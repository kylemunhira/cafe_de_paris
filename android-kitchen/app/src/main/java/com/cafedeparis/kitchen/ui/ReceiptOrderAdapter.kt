package com.cafedeparis.kitchen.ui

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.cafedeparis.kitchen.R
import com.cafedeparis.kitchen.data.KitchenOrder
import com.cafedeparis.kitchen.databinding.ItemReceiptOrderBinding

class ReceiptOrderAdapter(
    private val onOrderClick: (KitchenOrder) -> Unit,
) : ListAdapter<KitchenOrder, ReceiptOrderAdapter.ViewHolder>(Diff) {

    var selectedOrderId: Int? = null
    var openOrders: List<KitchenOrder> = emptyList()

    private fun tableOrdersFor(order: KitchenOrder): List<KitchenOrder> {
        if (order.status != "open") return listOf(order)
        val table = order.table_number.trim()
        if (table.isEmpty()) return listOf(order)
        return openOrders.filter {
            it.status == "open" && it.order_type == "dine_in" && it.table_number == table
        }
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val binding = ItemReceiptOrderBinding.inflate(LayoutInflater.from(parent.context), parent, false)
        return ViewHolder(binding)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        holder.bind(getItem(position))
    }

    inner class ViewHolder(
        private val binding: ItemReceiptOrderBinding,
    ) : RecyclerView.ViewHolder(binding.root) {
        fun bind(order: KitchenOrder) {
            val tableOrders = tableOrdersFor(order)
            val displayTotal = if (tableOrders.size > 1) {
                tableOrders.sumOf { it.total_amount.toDoubleOrNull() ?: 0.0 }
            } else {
                order.total_amount.toDoubleOrNull() ?: 0.0
            }
            binding.orderId.text = "#${order.id}"
            binding.orderTotal.text = ProductAdapter.formatMoney(displayTotal.toString())
            val typeLabel = order.order_type.replace("_", " ").replaceFirstChar { it.uppercase() }
            val table = if (order.table_number.isNotBlank()) " · Table ${order.table_number}" else ""
            val combined = if (tableOrders.size > 1) " · ${tableOrders.size} orders on table" else ""
            binding.orderMeta.text = "$typeLabel$table$combined · ${order.items.size} items"
            binding.orderKitchenStatus.text = if (order.status == "unpaid") {
                binding.root.context.getString(R.string.status_unpaid)
            } else {
                order.kitchen_status.replace("_", " ")
                    .replaceFirstChar { it.uppercase() }
            }

            val selected = order.id == selectedOrderId
            val stroke = if (selected) R.color.accent else android.R.color.transparent
            binding.root.strokeColor = ContextCompat.getColor(binding.root.context, stroke)
            binding.root.strokeWidth = if (selected) 4 else 0
            binding.root.setOnClickListener { onOrderClick(order) }
        }
    }

    companion object {
        private val Diff = object : DiffUtil.ItemCallback<KitchenOrder>() {
            override fun areItemsTheSame(oldItem: KitchenOrder, newItem: KitchenOrder) = oldItem.id == newItem.id
            override fun areContentsTheSame(oldItem: KitchenOrder, newItem: KitchenOrder) = oldItem == newItem
        }
    }
}
