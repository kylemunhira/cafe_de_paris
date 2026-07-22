package com.cafedeparis.kitchen

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.core.widget.doAfterTextChanged
import androidx.lifecycle.lifecycleScope
import com.cafedeparis.kitchen.data.ApiClient
import com.cafedeparis.kitchen.data.ApiException
import com.cafedeparis.kitchen.data.AppConfig
import com.cafedeparis.kitchen.data.InventoryItem
import com.cafedeparis.kitchen.data.Product
import com.cafedeparis.kitchen.data.ProductionOrder
import com.cafedeparis.kitchen.data.ProductionPreview
import com.cafedeparis.kitchen.data.SessionManager
import com.cafedeparis.kitchen.databinding.ActivityBakeryProductionBinding
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.DecimalFormat
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class BakeryProductionActivity : KeepScreenOnActivity() {

    private lateinit var binding: ActivityBakeryProductionBinding
    private lateinit var session: SessionManager
    private lateinit var api: ApiClient
    private var products: List<Product> = emptyList()
    private var history: List<ProductionOrder> = emptyList()
    private var inventory: List<InventoryItem> = emptyList()
    private var preview: ProductionPreview? = null
    private var previewJob: Job? = null
    private var errorHideJob: Job? = null
    private var loading = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityBakeryProductionBinding.inflate(layoutInflater)
        setContentView(binding.root)

        session = SessionManager(this)
        api = ApiClient(session, AppConfig(this))
        if (!session.isLoggedIn || !session.canAccessBakery) {
            returnToLogin()
            return
        }

        binding.branchLabel.text = getString(
            R.string.bakery_branch_label,
            session.branchName.orEmpty(),
        )
        binding.staffLabel.text = session.displayName.orEmpty()
        binding.transfersButton.setOnClickListener {
            startActivity(Intent(this, BakeryTransferActivity::class.java))
        }
        binding.refreshButton.setOnClickListener { loadPage() }
        binding.settingsButton.setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }
        binding.logoutButton.setOnClickListener { logout() }
        binding.recordButton.setOnClickListener { recordProduction() }
        binding.quantityInput.doAfterTextChanged { schedulePreview() }
        binding.productSpinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(
                parent: AdapterView<*>?,
                view: View?,
                position: Int,
                id: Long,
            ) {
                schedulePreview()
            }

            override fun onNothingSelected(parent: AdapterView<*>?) {
                clearPreview()
            }
        }

        loadPage()
    }

    override fun onDestroy() {
        previewJob?.cancel()
        errorHideJob?.cancel()
        super.onDestroy()
    }

    override fun onResume() {
        super.onResume()
        if (::api.isInitialized) {
            loadPage()
        }
    }

    private fun loadPage() {
        if (loading) return
        loading = true
        showLoading(true)
        binding.errorBanner.visibility = View.GONE
        lifecycleScope.launch {
            try {
                val data = withContext(Dispatchers.IO) {
                    PageData(
                        products = api.fetchBakeryProducts(),
                        history = api.fetchProductionOrders(),
                        inventory = api.fetchBakeryInventory(),
                    )
                }
                products = data.products
                history = data.history
                inventory = data.inventory
                populateProducts()
                renderHistory()
                renderStats()
                schedulePreview()
            } catch (err: ApiException) {
                handleApiError(err)
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message.orEmpty()))
            } finally {
                loading = false
                showLoading(false)
            }
        }
    }

    private fun populateProducts() {
        val labels = mutableListOf(getString(R.string.bakery_select_product))
        labels.addAll(products.map {
            if (it.category_name.isNullOrBlank()) it.name else "${it.name} (${it.category_name})"
        })
        val adapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, labels)
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        binding.productSpinner.adapter = adapter
        binding.productSpinner.isEnabled = products.isNotEmpty()
        if (products.isEmpty()) {
            binding.previewMessage.text = getString(R.string.bakery_no_products)
        }
    }

    private fun selectedProduct(): Product? {
        val index = binding.productSpinner.selectedItemPosition - 1
        return products.getOrNull(index)
    }

    private fun schedulePreview() {
        previewJob?.cancel()
        clearPreview()
        val product = selectedProduct() ?: return
        val quantity = binding.quantityInput.text?.toString()?.trim().orEmpty()
        if ((quantity.toDoubleOrNull() ?: 0.0) <= 0.0) return

        binding.previewMessage.text = getString(R.string.bakery_checking_ingredients)
        previewJob = lifecycleScope.launch {
            delay(350)
            try {
                val result = withContext(Dispatchers.IO) {
                    api.previewProduction(product.id, quantity)
                }
                preview = result
                renderPreview(result)
            } catch (err: ApiException) {
                if (err.statusCode == 401) {
                    handleApiError(err)
                } else {
                    binding.previewMessage.text = err.message
                }
            } catch (err: Exception) {
                binding.previewMessage.text =
                    getString(R.string.connection_failed, err.message.orEmpty())
            }
        }
    }

    private fun clearPreview() {
        preview = null
        binding.recordButton.isEnabled = false
        binding.previewLines.removeAllViews()
        if (products.isNotEmpty()) {
            binding.previewMessage.text = ""
        }
    }

    private fun renderPreview(result: ProductionPreview) {
        binding.previewLines.removeAllViews()
        if (result.lines.isNotEmpty()) {
            addRow(
                binding.previewLines,
                listOf(
                    getString(R.string.bakery_ingredient),
                    getString(R.string.bakery_required),
                    getString(R.string.bakery_available),
                    getString(R.string.bakery_status),
                ),
                bold = true,
            )
            result.lines.forEach { line ->
                addRow(
                    binding.previewLines,
                    listOf(
                        if (line.ingredientCategory.isBlank()) {
                            line.ingredientName
                        } else {
                            "${line.ingredientName}\n${line.ingredientCategory}"
                        },
                        formatQuantity(line.required),
                        formatQuantity(line.available),
                        getString(
                            if (line.sufficient) R.string.bakery_status_ok
                            else R.string.bakery_status_short,
                        ),
                    ),
                )
            }
        }
        binding.previewMessage.text = if (result.canProduce) {
            getString(
                R.string.bakery_ready_to_produce,
                formatQuantity(result.quantity),
                result.productName,
            )
        } else {
            getString(R.string.bakery_insufficient_ingredients)
        }
        binding.recordButton.isEnabled = result.canProduce
    }

    private fun recordProduction() {
        val product = selectedProduct() ?: return
        val quantity = binding.quantityInput.text?.toString()?.trim().orEmpty()
        if (preview?.canProduce != true) {
            Toast.makeText(
                this,
                R.string.bakery_resolve_shortages,
                Toast.LENGTH_SHORT,
            ).show()
            return
        }
        binding.recordButton.isEnabled = false
        showLoading(true)
        lifecycleScope.launch {
            try {
                val order = withContext(Dispatchers.IO) {
                    api.createProduction(product.id, quantity)
                }
                Toast.makeText(
                    this@BakeryProductionActivity,
                    getString(
                        R.string.bakery_production_recorded,
                        formatQuantity(order.quantity),
                        order.productName,
                    ),
                    Toast.LENGTH_LONG,
                ).show()
                binding.productSpinner.setSelection(0)
                binding.quantityInput.text?.clear()
                loadPage()
            } catch (err: ApiException) {
                handleApiError(err)
                schedulePreview()
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message.orEmpty()))
                schedulePreview()
            } finally {
                showLoading(false)
            }
        }
    }

    private fun renderHistory() {
        binding.historyLines.removeAllViews()
        if (history.isEmpty()) {
            addRow(
                binding.historyLines,
                listOf(getString(R.string.bakery_no_production)),
            )
            return
        }
        addRow(
            binding.historyLines,
            listOf(
                getString(R.string.bakery_when),
                getString(R.string.bakery_product),
                getString(R.string.bakery_qty),
                getString(R.string.bakery_recorded_by),
            ),
            bold = true,
        )
        history.forEach { order ->
            addRow(
                binding.historyLines,
                listOf(
                    formatDate(order.createdAt),
                    order.productName,
                    formatQuantity(order.quantity),
                    order.createdByName ?: "—",
                ),
            )
        }
    }

    private fun renderStats() {
        val quantities = inventory.associate { it.productId to (it.quantity.toDoubleOrNull() ?: 0.0) }
        val finishedSkus = products.count { (quantities[it.id] ?: 0.0) > 0.0 }
        val units = products.sumOf { quantities[it.id] ?: 0.0 }
        val today = SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date())
        val todayBatches = history.count { it.createdAt.startsWith(today) }
        binding.stockStat.text = getString(
            R.string.bakery_stock_stat,
            finishedSkus,
            formatQuantity(units.toString()),
        )
        binding.batchesStat.text = getString(
            R.string.bakery_batches_stat,
            todayBatches,
            history.size,
        )
    }

    private fun addRow(container: LinearLayout, values: List<String>, bold: Boolean = false) {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, 8, 0, 8)
        }
        values.forEach { value ->
            row.addView(
                TextView(this).apply {
                    text = value
                    setTextColor(getColor(R.color.text_primary))
                    textSize = 13f
                    if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD)
                },
                LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f),
            )
        }
        container.addView(row)
        container.addView(
            View(this).apply { setBackgroundColor(getColor(R.color.background)) },
            LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 1),
        )
    }

    private fun formatQuantity(value: String): String {
        return value.toDoubleOrNull()?.let { DecimalFormat("#,##0.##").format(it) } ?: value
    }

    private fun formatDate(value: String): String {
        return value.replace('T', ' ').take(16)
    }

    private fun showLoading(show: Boolean) {
        binding.progress.visibility = if (show) View.VISIBLE else View.GONE
        binding.refreshButton.isEnabled = !show
    }

    private fun handleApiError(err: ApiException) {
        if (err.statusCode == 401) {
            Toast.makeText(this, R.string.session_expired, Toast.LENGTH_LONG).show()
            logout()
        } else {
            showError(err.message ?: getString(R.string.bakery_load_failed))
        }
    }

    private fun showError(message: String) {
        binding.errorBanner.text = message
        binding.errorBanner.visibility = View.VISIBLE
        errorHideJob?.cancel()
        errorHideJob = lifecycleScope.launch {
            delay(ERROR_BANNER_MS)
            binding.errorBanner.visibility = View.GONE
        }
    }

    private fun logout() {
        session.clearLogin()
        returnToLogin()
    }

    private fun returnToLogin() {
        startActivity(
            Intent(this, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            },
        )
        finish()
    }

    private data class PageData(
        val products: List<Product>,
        val history: List<ProductionOrder>,
        val inventory: List<InventoryItem>,
    )

    companion object {
        private const val ERROR_BANNER_MS = 6_000L
    }
}
