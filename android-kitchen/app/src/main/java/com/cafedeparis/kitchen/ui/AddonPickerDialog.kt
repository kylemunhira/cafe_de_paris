package com.cafedeparis.kitchen.ui

import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.cafedeparis.kitchen.R
import com.cafedeparis.kitchen.data.CartAddon
import com.cafedeparis.kitchen.data.MenuAddon
import com.cafedeparis.kitchen.data.MenuAddonGroup
import com.cafedeparis.kitchen.data.Product
import com.cafedeparis.kitchen.databinding.DialogAddonPickerBinding
import com.google.android.material.chip.Chip
import com.google.android.material.chip.ChipGroup
import com.google.android.material.dialog.MaterialAlertDialogBuilder

object AddonPickerDialog {

    fun show(
        activity: AppCompatActivity,
        product: Product,
        onConfirm: (List<CartAddon>, String) -> Unit,
    ) {
        val binding = DialogAddonPickerBinding.inflate(activity.layoutInflater)
        val selections = linkedMapOf<Int, MutableSet<Int>>()
        val density = activity.resources.displayMetrics.density
        val groupSpacing = (12 * density).toInt()

        for (group in product.addon_groups.filter { groupHasAddons(it) }) {
            binding.addonGroupsContainer.addView(buildGroupSection(activity, group, selections, groupSpacing))
        }

        MaterialAlertDialogBuilder(activity)
            .setTitle(activity.getString(R.string.addon_picker_title, product.name))
            .setView(binding.root)
            .setNegativeButton(android.R.string.cancel, null)
            .setPositiveButton(R.string.add_to_cart) { _, _ ->
                val addons = collectSelectedAddons(product, selections)
                val notes = binding.addonNotesInput.text?.toString()?.trim().orEmpty()
                onConfirm(addons, notes)
            }
            .show()
    }

    private fun groupHasAddons(group: MenuAddonGroup): Boolean =
        group.addons.any { it.is_active }

    private fun buildGroupSection(
        activity: AppCompatActivity,
        group: MenuAddonGroup,
        selections: MutableMap<Int, MutableSet<Int>>,
        bottomMargin: Int,
    ): LinearLayout {
        val section = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT,
            ).apply { this.bottomMargin = bottomMargin }
        }

        val title = TextView(activity).apply {
            text = group.name
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            textSize = 14f
            setPadding(0, 0, 0, (6 * activity.resources.displayMetrics.density).toInt())
        }
        section.addView(title)

        val groupSelections = mutableSetOf<Int>()
        selections[group.id] = groupSelections

        val chipGroup = ChipGroup(activity).apply {
            isSingleSelection = group.selection_type == "single"
            isSelectionRequired = false
            chipSpacingHorizontal = (6 * activity.resources.displayMetrics.density).toInt()
            chipSpacingVertical = (6 * activity.resources.displayMetrics.density).toInt()
        }

        for (addon in group.addons.filter { it.is_active }) {
            chipGroup.addView(buildAddonChip(activity, addon))
        }

        chipGroup.setOnCheckedStateChangeListener { group, checkedIds ->
            groupSelections.clear()
            for (chipId in checkedIds) {
                val chip = group.findViewById<Chip>(chipId) ?: continue
                val addonId = chip.tag as? Int ?: continue
                groupSelections.add(addonId)
            }
        }

        section.addView(chipGroup)
        return section
    }

    private fun buildAddonChip(activity: AppCompatActivity, addon: MenuAddon): Chip {
        val price = addon.selling_price.toDoubleOrNull() ?: 0.0
        val label = if (price > 0.0) {
            activity.getString(
                R.string.addon_price_extra,
                addon.name,
                ProductAdapter.formatMoney(addon.selling_price),
            )
        } else {
            addon.name
        }
        return Chip(activity).apply {
            text = label
            isCheckable = true
            id = View.generateViewId()
            tag = addon.id
            gravity = Gravity.CENTER_VERTICAL
        }
    }

    private fun collectSelectedAddons(
        product: Product,
        selections: Map<Int, Set<Int>>,
    ): List<CartAddon> {
        val addons = mutableListOf<CartAddon>()
        for (group in product.addon_groups) {
            val selectedIds = selections[group.id].orEmpty()
            for (addon in group.addons) {
                if (addon.id in selectedIds) {
                    addons.add(
                        CartAddon(
                            id = addon.id,
                            name = addon.name,
                            price = addon.selling_price.toDoubleOrNull() ?: 0.0,
                        ),
                    )
                }
            }
        }
        return addons
    }
}
