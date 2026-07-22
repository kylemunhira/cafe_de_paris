package com.cafedeparis.kitchen

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.View
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.cafedeparis.kitchen.data.ApiClient
import com.cafedeparis.kitchen.data.ApiException
import com.cafedeparis.kitchen.data.AppConfig
import com.cafedeparis.kitchen.data.Branch
import com.cafedeparis.kitchen.data.DeliveryNote
import com.cafedeparis.kitchen.data.InventoryItem
import com.cafedeparis.kitchen.data.Product
import com.cafedeparis.kitchen.data.SessionManager
import com.cafedeparis.kitchen.databinding.ActivityBakeryTransferBinding
import com.cafedeparis.kitchen.print.EscPosPrinter
import com.cafedeparis.kitchen.print.PrinterException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.DecimalFormat

class BakeryTransferActivity : KeepScreenOnActivity() {

    private lateinit var binding: ActivityBakeryTransferBinding
    private lateinit var session: SessionManager
    private lateinit var api: ApiClient
    private val printer = EscPosPrinter()
    private var destinations: List<Branch> = emptyList()
    private var products: List<Product> = emptyList()
    private var inventory: List<InventoryItem> = emptyList()
    private val cart = mutableListOf<TransferCartLine>()
    private var loading = false
    private var statusReady = false
    private var errorHideJob: Job? = null

    private val bluetoothPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        if (!granted) {
            Toast.makeText(this, R.string.bluetooth_permission_required, Toast.LENGTH_LONG).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityBakeryTransferBinding.inflate(layoutInflater)
        setContentView(binding.root)
        session = SessionManager(this)
        api = ApiClient(session, AppConfig(this))
        if (!session.isLoggedIn || !session.canAccessBakery) {
            returnToLogin()
            return
        }

        binding.branchLabel.text = getString(
            R.string.bakery_transfer_branch_label,
            session.branchName.orEmpty(),
        )
        binding.staffLabel.text = session.displayName.orEmpty()
        binding.productionButton.setOnClickListener { finish() }
        binding.refreshButton.setOnClickListener { loadPage() }
        binding.settingsButton.setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }
        binding.logoutButton.setOnClickListener { logout() }
        binding.addLineButton.setOnClickListener { addCartLine() }
        binding.sendButton.setOnClickListener { confirmCreateTransfer() }
        configureStatusFilter()
        loadPage()
    }

    private fun configureStatusFilter() {
        val labels = listOf(
            getString(R.string.bakery_status_all),
            getString(R.string.bakery_status_requested),
            getString(R.string.bakery_status_approved),
            getString(R.string.bakery_status_dispatched),
            getString(R.string.bakery_status_delivered),
            getString(R.string.bakery_status_cancelled),
        )
        binding.statusSpinner.adapter = ArrayAdapter(
            this,
            android.R.layout.simple_spinner_item,
            labels,
        ).also {
            it.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        }
        binding.statusSpinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(
                parent: AdapterView<*>?,
                view: View?,
                position: Int,
                id: Long,
            ) {
                if (statusReady) loadHistory()
            }

            override fun onNothingSelected(parent: AdapterView<*>?) = Unit
        }
        statusReady = true
    }

    private fun selectedStatus(): String? {
        return STATUS_KEYS.getOrNull(binding.statusSpinner.selectedItemPosition)
    }

    private fun loadPage() {
        if (loading) return
        loading = true
        showLoading(true)
        binding.errorBanner.visibility = View.GONE
        lifecycleScope.launch {
            try {
                val data = withContext(Dispatchers.IO) {
                    TransferPageData(
                        destinations = api.fetchBakeryTransferDestinations(),
                        products = api.fetchBakeryProducts(),
                        inventory = api.fetchBakeryInventory(),
                        notes = api.fetchBakeryDeliveryNotes(selectedStatus()),
                    )
                }
                destinations = data.destinations
                products = data.products
                inventory = data.inventory
                populateSelectors()
                renderCart()
                renderHistory(data.notes)
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

    private fun loadHistory() {
        if (loading) return
        showLoading(true)
        lifecycleScope.launch {
            try {
                val notes = withContext(Dispatchers.IO) {
                    api.fetchBakeryDeliveryNotes(selectedStatus())
                }
                renderHistory(notes)
            } catch (err: ApiException) {
                handleApiError(err)
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message.orEmpty()))
            } finally {
                showLoading(false)
            }
        }
    }

    private fun populateSelectors() {
        binding.destinationSpinner.adapter = spinnerAdapter(
            listOf(getString(R.string.bakery_select_destination)) +
                destinations.map { it.name },
        )
        val stock = stockByProduct()
        binding.productSpinner.adapter = spinnerAdapter(
            listOf(getString(R.string.bakery_select_product)) +
                products.map {
                    getString(
                        R.string.bakery_product_with_stock,
                        it.name,
                        formatQuantity((stock[it.id] ?: 0.0).toString()),
                    )
                },
        )
        binding.destinationSpinner.isEnabled = destinations.isNotEmpty()
        binding.productSpinner.isEnabled = products.isNotEmpty()
        if (destinations.isEmpty()) {
            showError(getString(R.string.bakery_no_destinations))
        }
    }

    private fun spinnerAdapter(values: List<String>): ArrayAdapter<String> {
        return ArrayAdapter(this, android.R.layout.simple_spinner_item, values).also {
            it.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        }
    }

    private fun addCartLine() {
        val product = products.getOrNull(binding.productSpinner.selectedItemPosition - 1)
        if (product == null) {
            Toast.makeText(this, R.string.bakery_select_product_error, Toast.LENGTH_SHORT).show()
            return
        }
        val quantityText = binding.quantityInput.text?.toString()?.trim().orEmpty()
        val quantity = quantityText.toDoubleOrNull() ?: 0.0
        if (quantity <= 0.0) {
            Toast.makeText(this, R.string.bakery_transfer_quantity_error, Toast.LENGTH_SHORT).show()
            return
        }
        val existing = cart.filter { it.product.id == product.id }.sumOf { it.quantity }
        val available = stockByProduct()[product.id] ?: 0.0
        if (existing + quantity > available) {
            Toast.makeText(
                this,
                getString(
                    R.string.bakery_transfer_stock_error,
                    formatQuantity(available.toString()),
                ),
                Toast.LENGTH_LONG,
            ).show()
            return
        }
        val existingLine = cart.firstOrNull { it.product.id == product.id }
        if (existingLine == null) {
            cart.add(TransferCartLine(product, quantity))
        } else {
            existingLine.quantity += quantity
        }
        binding.productSpinner.setSelection(0)
        binding.quantityInput.text?.clear()
        renderCart()
    }

    private fun renderCart() {
        binding.cartLines.removeAllViews()
        cart.forEach { line ->
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = android.view.Gravity.CENTER_VERTICAL
                setPadding(0, 6, 0, 6)
            }
            row.addView(
                TextView(this).apply {
                    text = line.product.name
                    setTextColor(getColor(R.color.text_primary))
                },
                LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f),
            )
            row.addView(
                TextView(this).apply {
                    text = formatQuantity(line.quantity.toString())
                    setTextColor(getColor(R.color.text_primary))
                },
            )
            row.addView(
                Button(this).apply {
                    text = getString(R.string.remove)
                    setOnClickListener {
                        cart.remove(line)
                        renderCart()
                    }
                },
            )
            binding.cartLines.addView(row)
        }
        val total = cart.sumOf { it.quantity }
        binding.cartTotal.text = if (cart.isEmpty()) {
            getString(R.string.bakery_transfer_empty)
        } else {
            getString(
                R.string.bakery_transfer_total,
                cart.size,
                formatQuantity(total.toString()),
            )
        }
        binding.sendButton.isEnabled = cart.isNotEmpty() && destinations.isNotEmpty()
    }

    private fun confirmCreateTransfer() {
        val destination = destinations.getOrNull(
            binding.destinationSpinner.selectedItemPosition - 1,
        )
        if (destination == null) {
            Toast.makeText(this, R.string.bakery_select_destination_error, Toast.LENGTH_SHORT).show()
            return
        }
        if (cart.isEmpty()) return
        AlertDialog.Builder(this)
            .setTitle(R.string.bakery_create_delivery_note)
            .setMessage(getString(R.string.bakery_transfer_confirm, destination.name))
            .setNegativeButton(android.R.string.cancel, null)
            .setPositiveButton(R.string.bakery_send_transfer) { _, _ ->
                createTransfer(destination)
            }
            .show()
    }

    private fun createTransfer(destination: Branch) {
        showLoading(true)
        binding.sendButton.isEnabled = false
        val lines = cart.map { it.product.id to it.quantity.toString() }
        lifecycleScope.launch {
            try {
                val note = withContext(Dispatchers.IO) {
                    api.createBakeryDeliveryNote(destination.id, lines)
                }
                Toast.makeText(
                    this@BakeryTransferActivity,
                    getString(R.string.bakery_transfer_created, note.id),
                    Toast.LENGTH_LONG,
                ).show()
                cart.clear()
                binding.destinationSpinner.setSelection(0)
                loadPage()
            } catch (err: ApiException) {
                handleApiError(err)
                binding.sendButton.isEnabled = cart.isNotEmpty()
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message.orEmpty()))
                binding.sendButton.isEnabled = cart.isNotEmpty()
            } finally {
                showLoading(false)
            }
        }
    }

    private fun renderHistory(notes: List<DeliveryNote>) {
        binding.historyLines.removeAllViews()
        if (notes.isEmpty()) {
            addHistoryText(getString(R.string.bakery_no_transfers))
            return
        }
        notes.forEach { note ->
            val card = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(8, 10, 8, 10)
            }
            card.addView(TextView(this).apply {
                text = getString(
                    R.string.bakery_transfer_history_title,
                    note.id,
                    note.destinationName,
                    note.status.replaceFirstChar { it.uppercase() },
                )
                setTextColor(getColor(R.color.text_primary))
                setTypeface(typeface, android.graphics.Typeface.BOLD)
            })
            card.addView(TextView(this).apply {
                text = note.lines.joinToString("\n") {
                    "${it.productName} × ${formatQuantity(it.quantity)}"
                }
                setTextColor(getColor(R.color.text_primary))
            })
            card.addView(TextView(this).apply {
                text = getString(
                    R.string.bakery_transfer_history_meta,
                    formatQuantity(note.totalQuantity),
                    formatDate(note.createdAt),
                )
                setTextColor(getColor(R.color.text_muted))
            })
            card.addView(Button(this).apply {
                text = getString(R.string.bakery_print_delivery_note)
                setOnClickListener { printDeliveryNote(note) }
            })
            if (note.status == "requested") {
                card.addView(Button(this).apply {
                    text = getString(R.string.bakery_cancel_transfer)
                    setOnClickListener { confirmCancel(note) }
                })
            }
            binding.historyLines.addView(card)
            binding.historyLines.addView(
                View(this).apply { setBackgroundColor(getColor(R.color.background)) },
                LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 2),
            )
        }
    }

    private fun printDeliveryNote(note: DeliveryNote) {
        val printerAddress = session.printerAddress
        if (printerAddress.isNullOrBlank()) {
            Toast.makeText(this, R.string.printer_not_configured, Toast.LENGTH_LONG).show()
            startActivity(Intent(this, SettingsActivity::class.java))
            return
        }
        if (!hasBluetoothPermission()) {
            requestBluetoothPermission()
            return
        }
        showLoading(true)
        lifecycleScope.launch {
            try {
                withContext(Dispatchers.IO) {
                    printer.printDeliveryNote(printerAddress, note)
                }
                Toast.makeText(
                    this@BakeryTransferActivity,
                    R.string.bakery_delivery_note_printed,
                    Toast.LENGTH_SHORT,
                ).show()
            } catch (err: PrinterException) {
                showError(getString(R.string.print_failed, err.message.orEmpty()))
            } catch (_: SecurityException) {
                requestBluetoothPermission()
            } catch (err: Exception) {
                showError(getString(R.string.print_failed, err.message.orEmpty()))
            } finally {
                showLoading(false)
            }
        }
    }

    private fun hasBluetoothPermission(): Boolean {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.S ||
            ContextCompat.checkSelfPermission(
                this,
                Manifest.permission.BLUETOOTH_CONNECT,
            ) == PackageManager.PERMISSION_GRANTED
    }

    private fun requestBluetoothPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            bluetoothPermissionLauncher.launch(Manifest.permission.BLUETOOTH_CONNECT)
        }
    }

    private fun addHistoryText(message: String) {
        binding.historyLines.addView(TextView(this).apply {
            text = message
            setTextColor(getColor(R.color.text_muted))
            setPadding(0, 12, 0, 12)
        })
    }

    private fun confirmCancel(note: DeliveryNote) {
        AlertDialog.Builder(this)
            .setTitle(R.string.bakery_cancel_transfer)
            .setMessage(getString(R.string.bakery_cancel_transfer_confirm, note.id))
            .setNegativeButton(android.R.string.cancel, null)
            .setPositiveButton(R.string.bakery_cancel_transfer) { _, _ -> cancelTransfer(note) }
            .show()
    }

    private fun cancelTransfer(note: DeliveryNote) {
        showLoading(true)
        lifecycleScope.launch {
            try {
                withContext(Dispatchers.IO) { api.cancelBakeryDeliveryNote(note.id) }
                Toast.makeText(
                    this@BakeryTransferActivity,
                    R.string.bakery_transfer_cancelled,
                    Toast.LENGTH_SHORT,
                ).show()
                loadPage()
            } catch (err: ApiException) {
                handleApiError(err)
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message.orEmpty()))
            } finally {
                showLoading(false)
            }
        }
    }

    private fun stockByProduct(): Map<Int, Double> {
        return inventory.associate { it.productId to (it.quantity.toDoubleOrNull() ?: 0.0) }
    }

    private fun formatQuantity(value: String): String {
        return value.toDoubleOrNull()?.let { DecimalFormat("#,##0.##").format(it) } ?: value
    }

    private fun formatDate(value: String): String = value.replace('T', ' ').take(16)

    private fun showLoading(show: Boolean) {
        binding.progress.visibility = if (show) View.VISIBLE else View.GONE
        binding.refreshButton.isEnabled = !show
    }

    private fun handleApiError(err: ApiException) {
        if (err.statusCode == 401) {
            Toast.makeText(this, R.string.session_expired, Toast.LENGTH_LONG).show()
            logout()
        } else {
            showError(err.message ?: getString(R.string.bakery_transfer_load_failed))
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

    private data class TransferCartLine(
        val product: Product,
        var quantity: Double,
    )

    private data class TransferPageData(
        val destinations: List<Branch>,
        val products: List<Product>,
        val inventory: List<InventoryItem>,
        val notes: List<DeliveryNote>,
    )

    companion object {
        private val STATUS_KEYS = listOf(null, "requested", "approved", "dispatched", "delivered", "cancelled")
        private const val ERROR_BANNER_MS = 6_000L
    }
}
