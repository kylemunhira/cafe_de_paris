package com.cafedeparis.kitchen.ui

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.RecyclerView
import com.cafedeparis.kitchen.databinding.ItemCategoryCardBinding

class CategoryChipAdapter(
    private val onCategorySelected: (Int?) -> Unit,
) : RecyclerView.Adapter<CategoryChipAdapter.ViewHolder>() {

    data class Chip(val id: Int?, val name: String)

    private var items: List<Chip> = emptyList()
    var selectedId: Int? = null
        private set

    fun submit(categories: List<Chip>) {
        items = categories
        notifyDataSetChanged()
    }

    fun select(id: Int?) {
        selectedId = id
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val binding = ItemCategoryCardBinding.inflate(LayoutInflater.from(parent.context), parent, false)
        return ViewHolder(binding)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        holder.bind(items[position])
    }

    override fun getItemCount() = items.size

    inner class ViewHolder(
        private val binding: ItemCategoryCardBinding,
    ) : RecyclerView.ViewHolder(binding.root) {
        fun bind(chip: Chip) {
            binding.categoryName.text = chip.name
            binding.root.isChecked = chip.id == selectedId
            binding.root.setOnClickListener {
                selectedId = chip.id
                notifyDataSetChanged()
                onCategorySelected(chip.id)
            }
        }
    }
}
