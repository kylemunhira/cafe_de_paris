package com.cafedeparis.kitchen.ui

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.cafedeparis.kitchen.data.CartLine
import com.cafedeparis.kitchen.databinding.ItemCartLineBinding

class CartLineAdapter(
    private val editable: Boolean,
    private val onQuantityChange: (String, Double) -> Unit,
) : ListAdapter<CartLine, CartLineAdapter.ViewHolder>(Diff) {

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val binding = ItemCartLineBinding.inflate(LayoutInflater.from(parent.context), parent, false)
        return ViewHolder(binding)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        holder.bind(getItem(position))
    }

    inner class ViewHolder(
        private val binding: ItemCartLineBinding,
    ) : RecyclerView.ViewHolder(binding.root) {
        fun bind(line: CartLine) {
            binding.lineName.text = line.name
            val summary = buildLineSummary(line)
            binding.lineMeta.text = if (summary.isNotBlank()) {
                "$summary\n${ProductAdapter.formatMoney(line.price.toString())} each"
            } else {
                "${ProductAdapter.formatMoney(line.price.toString())} each"
            }
            binding.lineQty.text = formatQty(line.quantity)
            binding.increaseButton.visibility = if (editable) android.view.View.VISIBLE else android.view.View.GONE
            binding.decreaseButton.visibility = if (editable) android.view.View.VISIBLE else android.view.View.GONE
            binding.increaseButton.setOnClickListener {
                onQuantityChange(line.lineKey, line.quantity + 1)
            }
            binding.decreaseButton.setOnClickListener {
                onQuantityChange(line.lineKey, line.quantity - 1)
            }
            binding.root.contentDescription = "${line.name} ${formatQty(line.quantity)}"
        }

        private fun buildLineSummary(line: CartLine): String {
            val parts = mutableListOf<String>()
            if (line.addons.isNotEmpty()) {
                parts.add(line.addons.joinToString(", ") { it.name })
            }
            if (line.notes.isNotBlank()) {
                parts.add("Note: ${line.notes}")
            }
            return parts.joinToString(" · ")
        }
    }

    companion object {
        private val Diff = object : DiffUtil.ItemCallback<CartLine>() {
            override fun areItemsTheSame(oldItem: CartLine, newItem: CartLine) =
                oldItem.lineKey == newItem.lineKey

            override fun areContentsTheSame(oldItem: CartLine, newItem: CartLine) = oldItem == newItem
        }

        private fun formatQty(value: Double): String {
            return if (value % 1.0 == 0.0) {
                value.toInt().toString()
            } else {
                String.format(java.util.Locale.US, "%.2f", value)
            }
        }
    }
}
