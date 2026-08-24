package com.cafedeparis.kitchen.ui

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.cafedeparis.kitchen.R
import com.cafedeparis.kitchen.data.KitchenOrder
import com.cafedeparis.kitchen.data.TaxMath
import com.cafedeparis.kitchen.data.receiptHeaderLabel
import com.cafedeparis.kitchen.databinding.ItemReceiptOrderBinding

class ReceiptOrderAdapter(
    private val onOrderClick: (KitchenOrder) -> Unit,
    private val onOrderLongClick: ((KitchenOrder) -> Unit)? = null,
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
            val goodsTotal = if (tableOrders.size > 1) {
                tableOrders.sumOf { it.total_amount.toDoubleOrNull() ?: 0.0 }
            } else {
                order.total_amount.toDoubleOrNull() ?: 0.0
            }
            val applyZta = order.branch_fiscalization_enabled ||
                tableOrders.any { it.branch_fiscalization_enabled }
            val displayTotal = TaxMath.splitInclusiveTotal(
                goodsTotal,
                applyZta = applyZta,
            ).total
            binding.orderId.text = order.receiptHeaderLabel()
            binding.orderTotal.text = ProductAdapter.formatMoney(displayTotal)
            val combined = if (tableOrders.size > 1) "${tableOrders.size} orders on table · " else ""
            binding.orderMeta.text = "$combined${order.items.size} items"
            binding.orderItemsPreview.text = formatOrderItemsPreview(order)
            binding.orderItemsPreview.visibility =
                if (order.items.isEmpty()) android.view.View.GONE else android.view.View.VISIBLE
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
            binding.root.setOnLongClickListener {
                val handler = onOrderLongClick ?: return@setOnLongClickListener false
                handler(order)
                true
            }
        }

        private fun formatOrderItemsPreview(order: KitchenOrder, maxItems: Int = 6): String {
            if (order.items.isEmpty()) return ""
            val parts = order.items.take(maxItems).map { item ->
                val qty = item.quantity.toDoubleOrNull() ?: 1.0
                val qtyLabel = when {
                    qty == 1.0 -> ""
                    qty % 1.0 == 0.0 -> "${qty.toInt()}× "
                    else -> String.format(java.util.Locale.US, "%.2f× ", qty)
                }
                "$qtyLabel${item.product_name}"
            }
            val more = if (order.items.size > maxItems) {
                " +${order.items.size - maxItems} more"
            } else {
                ""
            }
            return parts.joinToString(", ") + more
        }
    }

    companion object {
        private val Diff = object : DiffUtil.ItemCallback<KitchenOrder>() {
            override fun areItemsTheSame(oldItem: KitchenOrder, newItem: KitchenOrder) = oldItem.id == newItem.id
            override fun areContentsTheSame(oldItem: KitchenOrder, newItem: KitchenOrder) = oldItem == newItem
        }
    }
}
