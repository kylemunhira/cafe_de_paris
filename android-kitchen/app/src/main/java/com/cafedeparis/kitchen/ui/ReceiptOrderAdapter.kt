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
            binding.orderId.text = "#${order.id}"
            binding.orderTotal.text = ProductAdapter.formatMoney(order.total_amount)
            val typeLabel = order.order_type.replace("_", " ").replaceFirstChar { it.uppercase() }
            val table = if (order.table_number.isNotBlank()) " · Table ${order.table_number}" else ""
            binding.orderMeta.text = "$typeLabel$table · ${order.items.size} items"
            binding.orderKitchenStatus.text = order.kitchen_status.replace("_", " ")
                .replaceFirstChar { it.uppercase() }

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
