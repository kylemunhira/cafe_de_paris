package com.cafedeparis.kitchen.ui

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.cafedeparis.kitchen.data.Product
import com.cafedeparis.kitchen.databinding.ItemProductBinding
import java.text.NumberFormat
import java.util.Locale

class ProductAdapter(
    private val onProductClick: (Product) -> Unit,
) : ListAdapter<Product, ProductAdapter.ViewHolder>(Diff) {

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val binding = ItemProductBinding.inflate(LayoutInflater.from(parent.context), parent, false)
        return ViewHolder(binding)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        holder.bind(getItem(position))
    }

    inner class ViewHolder(
        private val binding: ItemProductBinding,
    ) : RecyclerView.ViewHolder(binding.root) {
        fun bind(product: Product) {
            binding.productName.text = product.name
            binding.productPrice.text = formatMoney(product.selling_price)
            binding.productAddonHint.visibility =
                if (product.hasActiveAddons()) android.view.View.VISIBLE else android.view.View.GONE
            binding.root.setOnClickListener { onProductClick(product) }
        }
    }

    companion object {
        private val Diff = object : DiffUtil.ItemCallback<Product>() {
            override fun areItemsTheSame(oldItem: Product, newItem: Product) = oldItem.id == newItem.id
            override fun areContentsTheSame(oldItem: Product, newItem: Product) = oldItem == newItem
        }

        fun formatMoney(value: String): String {
            val amount = value.toDoubleOrNull() ?: 0.0
            return NumberFormat.getCurrencyInstance(Locale.US).format(amount)
        }
    }
}
