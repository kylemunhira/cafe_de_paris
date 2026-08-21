package com.cafedeparis.kitchen.ui

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.cafedeparis.kitchen.R
import com.cafedeparis.kitchen.data.KitchenOrder
import com.cafedeparis.kitchen.data.receiptHeaderLabel
import com.cafedeparis.kitchen.databinding.ItemFiscalInvoiceBinding

class FiscalInvoiceAdapter(
    private val canApprove: Boolean,
    private val onApprove: (KitchenOrder) -> Unit,
    private val onReprint: (KitchenOrder) -> Unit,
) : ListAdapter<KitchenOrder, FiscalInvoiceAdapter.ViewHolder>(Diff) {

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val binding = ItemFiscalInvoiceBinding.inflate(
            LayoutInflater.from(parent.context),
            parent,
            false,
        )
        return ViewHolder(binding)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        holder.bind(getItem(position))
    }

    inner class ViewHolder(
        private val binding: ItemFiscalInvoiceBinding,
    ) : RecyclerView.ViewHolder(binding.root) {
        fun bind(order: KitchenOrder) {
            val context = binding.root.context
            val proforma = order.receipt_number?.takeIf { it.isNotBlank() }
            binding.fiscalInvoiceTitle.text = if (proforma != null) {
                context.getString(R.string.fiscal_invoice_proforma, proforma)
            } else {
                order.receiptHeaderLabel()
            }
            val location = when {
                order.order_type == "takeaway" -> context.getString(R.string.order_type_takeaway)
                order.table_number.isNotBlank() ->
                    context.getString(R.string.fiscal_invoice_table, order.table_number)
                else -> context.getString(R.string.order_type_dine_in)
            }
            binding.fiscalInvoiceMeta.text = context.getString(
                R.string.fiscal_invoice_meta,
                order.id,
                location,
            )
            binding.fiscalInvoiceTotal.text = ProductAdapter.formatMoney(order.total_amount)

            val status = order.fiscal_approval_status.orEmpty()
            when (status) {
                "pending" -> {
                    binding.fiscalInvoiceStatus.text =
                        context.getString(R.string.fiscal_invoice_status_pending)
                    binding.fiscalInvoiceStatus.setTextColor(
                        ContextCompat.getColor(context, R.color.status_pending),
                    )
                    binding.fiscalInvoiceApproveButton.visibility =
                        if (canApprove) View.VISIBLE else View.GONE
                    binding.fiscalInvoiceReprintButton.visibility = View.GONE
                }
                "approved" -> {
                    val fiscalNo = order.fiscal_receipt_number?.takeIf { it.isNotBlank() }
                    binding.fiscalInvoiceStatus.text = if (fiscalNo != null) {
                        context.getString(R.string.fiscal_invoice_status_approved_no, fiscalNo)
                    } else {
                        context.getString(R.string.fiscal_invoice_status_approved)
                    }
                    binding.fiscalInvoiceStatus.setTextColor(
                        ContextCompat.getColor(context, R.color.status_ready),
                    )
                    binding.fiscalInvoiceApproveButton.visibility = View.GONE
                    binding.fiscalInvoiceReprintButton.visibility = View.VISIBLE
                }
                "failed" -> {
                    binding.fiscalInvoiceStatus.text =
                        context.getString(R.string.fiscal_invoice_status_failed)
                    binding.fiscalInvoiceStatus.setTextColor(
                        ContextCompat.getColor(context, R.color.error),
                    )
                    binding.fiscalInvoiceApproveButton.visibility =
                        if (canApprove) View.VISIBLE else View.GONE
                    binding.fiscalInvoiceReprintButton.visibility = View.GONE
                }
                else -> {
                    binding.fiscalInvoiceStatus.text = status.ifBlank {
                        context.getString(R.string.fiscal_day_status_unknown)
                    }
                    binding.fiscalInvoiceStatus.setTextColor(
                        ContextCompat.getColor(context, R.color.text_muted),
                    )
                    binding.fiscalInvoiceApproveButton.visibility = View.GONE
                    binding.fiscalInvoiceReprintButton.visibility = View.GONE
                }
            }

            binding.fiscalInvoiceApproveButton.setOnClickListener { onApprove(order) }
            binding.fiscalInvoiceReprintButton.setOnClickListener { onReprint(order) }
        }
    }

    private object Diff : DiffUtil.ItemCallback<KitchenOrder>() {
        override fun areItemsTheSame(oldItem: KitchenOrder, newItem: KitchenOrder): Boolean =
            oldItem.id == newItem.id

        override fun areContentsTheSame(oldItem: KitchenOrder, newItem: KitchenOrder): Boolean =
            oldItem == newItem
    }
}
