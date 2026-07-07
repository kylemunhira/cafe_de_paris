package com.cafedeparis.kitchen.ui

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.cafedeparis.kitchen.R
import com.cafedeparis.kitchen.data.DiningTable
import com.cafedeparis.kitchen.databinding.ItemDiningTableBinding

class DiningTableAdapter(
    private val occupiedNames: Set<String>,
    private val selectedName: String?,
    private val onTableClick: (DiningTable) -> Unit,
) : ListAdapter<DiningTable, DiningTableAdapter.ViewHolder>(Diff) {

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val binding = ItemDiningTableBinding.inflate(LayoutInflater.from(parent.context), parent, false)
        return ViewHolder(binding)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        holder.bind(getItem(position))
    }

    inner class ViewHolder(
        private val binding: ItemDiningTableBinding,
    ) : RecyclerView.ViewHolder(binding.root) {
        fun bind(table: DiningTable) {
            val context = binding.root.context
            val occupied = table.name in occupiedNames
            val selected = table.name == selectedName

            binding.tableName.text = table.name
            binding.tableStatus.text = if (occupied) {
                context.getString(R.string.table_in_use)
            } else {
                context.getString(R.string.table_available)
            }
            binding.tableStatus.setTextColor(
                ContextCompat.getColor(
                    context,
                    if (occupied) R.color.status_pending else R.color.status_ready,
                ),
            )

            val strokeColor = when {
                selected -> R.color.accent
                occupied -> R.color.status_pending
                else -> android.R.color.transparent
            }
            binding.root.strokeColor = ContextCompat.getColor(context, strokeColor)
            binding.root.strokeWidth = if (selected || occupied) 4 else 0

            binding.root.setOnClickListener { onTableClick(table) }
        }
    }

    companion object {
        private val Diff = object : DiffUtil.ItemCallback<DiningTable>() {
            override fun areItemsTheSame(oldItem: DiningTable, newItem: DiningTable) = oldItem.id == newItem.id
            override fun areContentsTheSame(oldItem: DiningTable, newItem: DiningTable) = oldItem == newItem
        }
    }
}
