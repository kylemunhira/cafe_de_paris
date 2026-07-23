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
                val addonText = item.addons.joinToString(", ") { "+ ${it.name}" }
                val noteText = if (item.notes.isNotBlank()) " (${item.notes})" else ""
                val suffix = listOf(addonText, noteText).filter { it.isNotBlank() }.joinToString(" ")
                "$qty x ${item.product_name}$suffix"
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
                var value = iso.trim()
                if (value.endsWith("Z", ignoreCase = true)) {
                    value = value.dropLast(1) + "+00:00"
                }
                value = value.replace(Regex("\\.\\d+"), "")
                val hasOffset = Regex("[+-]\\d{2}:\\d{2}$").containsMatchIn(value)
                val parser = if (hasOffset) {
                    SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US)
                } else {
                    SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US).apply {
                        timeZone = TimeZone.getTimeZone("UTC")
                    }
                }
                parser.isLenient = false
                val date = parser.parse(value) ?: return iso
                SimpleDateFormat("HH:mm", Locale.US).format(date)
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
