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
    private val disabledNames: Set<String> = emptySet(),
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
            val disabled = table.name in disabledNames

            binding.tableName.text = table.name
            binding.tableStatus.text = when {
                disabled -> context.getString(R.string.table_current)
                occupied -> context.getString(R.string.table_in_use)
                else -> context.getString(R.string.table_available)
            }
            binding.tableStatus.setTextColor(
                ContextCompat.getColor(
                    context,
                    when {
                        disabled -> R.color.text_muted
                        occupied -> R.color.status_pending
                        else -> R.color.status_ready
                    },
                ),
            )

            val strokeColor = when {
                disabled -> android.R.color.transparent
                selected -> R.color.accent
                occupied -> R.color.status_pending
                else -> android.R.color.transparent
            }
            binding.root.strokeColor = ContextCompat.getColor(context, strokeColor)
            binding.root.strokeWidth = if (!disabled && (selected || occupied)) 4 else 0
            binding.root.alpha = if (disabled) 0.45f else 1f
            binding.root.isEnabled = !disabled
            binding.root.setOnClickListener {
                if (!disabled) onTableClick(table)
            }
        }
    }

    companion object {
        private val Diff = object : DiffUtil.ItemCallback<DiningTable>() {
            override fun areItemsTheSame(oldItem: DiningTable, newItem: DiningTable) = oldItem.id == newItem.id
            override fun areContentsTheSame(oldItem: DiningTable, newItem: DiningTable) = oldItem == newItem
        }
    }
}
