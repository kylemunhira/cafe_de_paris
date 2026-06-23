package com.cafedeparis.kitchen.ui

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.cafedeparis.kitchen.R
import com.cafedeparis.kitchen.data.KitchenOrder
import com.cafedeparis.kitchen.databinding.ItemOrderBinding
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone

class OrderAdapter : ListAdapter<KitchenOrder, OrderAdapter.OrderViewHolder>(Diff) {

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): OrderViewHolder {
        val binding = ItemOrderBinding.inflate(LayoutInflater.from(parent.context), parent, false)
        return OrderViewHolder(binding)
    }

    override fun onBindViewHolder(holder: OrderViewHolder, position: Int) {
        holder.bind(getItem(position))
    }

    class OrderViewHolder(private val binding: ItemOrderBinding) :
        RecyclerView.ViewHolder(binding.root) {

        fun bind(order: KitchenOrder) {
            binding.orderTitle.text = "Order #${order.id}"
            binding.orderMeta.text = buildMeta(order)
            binding.orderItems.text = order.items.joinToString("\n") { item ->
                val qty = item.quantity.toDoubleOrNull()?.let {
                    String.format(Locale.US, "%.2f", it)
                } ?: item.quantity
                "$qty x ${item.product_name}"
            }.ifBlank { "No items" }

            val statusColor = when (order.kitchen_status) {
                "ready" -> R.color.status_ready
                "preparing" -> R.color.status_preparing
                else -> R.color.status_pending
            }
            binding.orderStatus.text = order.kitchen_status.replaceFirstChar {
                if (it.isLowerCase()) it.titlecase(Locale.getDefault()) else it.toString()
            }
            binding.orderStatus.setTextColor(
                ContextCompat.getColor(binding.root.context, statusColor)
            )
        }

        private fun buildMeta(order: KitchenOrder): String {
            val type = when (order.order_type) {
                "dine_in" -> "Dine in"
                else -> "Takeaway"
            }
            val table = if (order.table_number.isNotBlank()) " · Table ${order.table_number}" else ""
            return "$type$table · ${formatDate(order.created_at)}"
        }

        private fun formatDate(iso: String): String {
            return try {
                val parser = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US).apply {
                    timeZone = TimeZone.getTimeZone("UTC")
                }
                val formatter = SimpleDateFormat("HH:mm", Locale.US)
                val date = parser.parse(iso.substring(0, 19))
                formatter.format(date!!)
            } catch (_: Exception) {
                iso
            }
        }
    }

    private object Diff : DiffUtil.ItemCallback<KitchenOrder>() {
        override fun areItemsTheSame(oldItem: KitchenOrder, newItem: KitchenOrder): Boolean {
            return oldItem.id == newItem.id
        }

        override fun areContentsTheSame(oldItem: KitchenOrder, newItem: KitchenOrder): Boolean {
            return oldItem == newItem
        }
    }
}
