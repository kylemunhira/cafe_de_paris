package com.cafedeparis.kitchen

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.LayoutInflater
import android.view.View
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.EditText
import android.widget.GridLayout
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import android.view.ViewGroup
import android.util.TypedValue
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.GridLayoutManager
import androidx.recyclerview.widget.LinearLayoutManager
import com.google.android.material.button.MaterialButton
import com.cafedeparis.kitchen.data.ApiClient
import com.cafedeparis.kitchen.data.ApiException
import com.cafedeparis.kitchen.data.AppConfig
import com.cafedeparis.kitchen.data.CartLine
import com.cafedeparis.kitchen.data.Currency
import com.cafedeparis.kitchen.data.Customer
import com.cafedeparis.kitchen.data.DiningTable
import com.cafedeparis.kitchen.data.KitchenOrder
import com.cafedeparis.kitchen.data.OrderSlipPrintOptions
import com.cafedeparis.kitchen.data.PaymentOptionLine
import com.cafedeparis.kitchen.data.Product
import com.cafedeparis.kitchen.data.SessionManager
import com.cafedeparis.kitchen.data.StockTake
import com.cafedeparis.kitchen.data.Supplier
import com.cafedeparis.kitchen.databinding.ActivityPosBinding
import com.cafedeparis.kitchen.databinding.DialogCustomerPaymentBinding
import com.cafedeparis.kitchen.databinding.DialogDayEndBinding
import java.util.Locale
import com.cafedeparis.kitchen.databinding.DialogExpenseBinding
import com.cafedeparis.kitchen.databinding.DialogStockTakeBinding
import com.cafedeparis.kitchen.databinding.DialogTablePickerBinding
import com.cafedeparis.kitchen.print.EscPosPrinter
import com.cafedeparis.kitchen.print.PrinterException
import com.cafedeparis.kitchen.data.cartLineKey
import com.cafedeparis.kitchen.ui.AddonPickerDialog
import com.cafedeparis.kitchen.ui.CartLineAdapter
import com.cafedeparis.kitchen.ui.CategoryChipAdapter
import com.cafedeparis.kitchen.ui.DiningTableAdapter
import com.cafedeparis.kitchen.ui.ProductAdapter
import com.cafedeparis.kitchen.ui.ReceiptOrderAdapter
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.textfield.TextInputEditText
import com.google.android.material.textfield.TextInputLayout
import java.text.SimpleDateFormat
import java.util.Date
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class PosActivity : KeepScreenOnActivity() {

    private lateinit var binding: ActivityPosBinding
    private lateinit var session: SessionManager
    private lateinit var config: AppConfig
    private lateinit var api: ApiClient

    private val cart = linkedMapOf<String, CartLine>()
    private var products: List<Product> = emptyList()
    private var allCurrencies: List<Currency> = emptyList()
    private var currencies: List<Currency> = emptyList()
    private var suppliers: List<Supplier> = emptyList()
    private var customers: List<Customer> = emptyList()
    private var diningTables: List<DiningTable> = emptyList()
    private var openOrders: List<KitchenOrder> = emptyList()
    private var selectedOrder: KitchenOrder? = null
    private var receiptPaymentOrderId: Int? = null
    private var selectedTableName: String? = null
    private var activeCategoryId: Int? = null
    private var searchQuery: String = ""
    private var posMode: PosMode = PosMode.ORDER
    private var paymentMethod: PaymentMethod = PaymentMethod.CASH
    private var selectedCurrencyId: Int? = null
    private var tablePickerDialog: androidx.appcompat.app.AlertDialog? = null
    private var dayEndDialog: androidx.appcompat.app.AlertDialog? = null
    private var expenseDialog: androidx.appcompat.app.AlertDialog? = null
    private var stockTakeDialog: androidx.appcompat.app.AlertDialog? = null
    private var customerPaymentDialog: androidx.appcompat.app.AlertDialog? = null
    private var activeStockTake: StockTake? = null
    private var stockTakeLineInputs: MutableMap<Int, TextInputEditText> = linkedMapOf()
    private var refreshJob: Job? = null
    private val printer = EscPosPrinter()

    private val bluetoothPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (!granted) {
            Toast.makeText(this, R.string.bluetooth_permission_required, Toast.LENGTH_LONG).show()
        }
    }

    private val productAdapter = ProductAdapter { product -> handleProductTap(product) }
    private val cartAdapter = CartLineAdapter(editable = true) { lineKey, qty ->
        updateCartQuantity(lineKey, qty)
    }
    private val receiptCartAdapter = CartLineAdapter(editable = false) { _, _ -> }
    private val receiptAdapter = ReceiptOrderAdapter(::onReceiptOrderSelected)
    private val categoryAdapter = CategoryChipAdapter { categoryId ->
        activeCategoryId = categoryId
        renderProducts()
    }

    private fun onReceiptOrderSelected(order: KitchenOrder) {
        selectedOrder = order
        receiptAdapter.selectedOrderId = order.id
        receiptAdapter.notifyDataSetChanged()
        renderReceiptPanel()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!SessionManager(this).isLoggedIn || !SessionManager(this).canAccessPos) {
            finish()
            return
        }

        binding = ActivityPosBinding.inflate(layoutInflater)
        setContentView(binding.root)

        session = SessionManager(this)
        config = AppConfig(this)
        api = ApiClient(session, config)

        binding.branchLabel.text = getString(R.string.pos_branch_label, session.branchName ?: "")
        binding.staffLabel.text = session.displayName ?: ""

        binding.productList.layoutManager = GridLayoutManager(this, 3)
        binding.productList.adapter = productAdapter
        binding.categoryList.layoutManager = LinearLayoutManager(this, LinearLayoutManager.HORIZONTAL, false)
        binding.categoryList.adapter = categoryAdapter
        binding.cartList.layoutManager = LinearLayoutManager(this)
        binding.cartList.adapter = cartAdapter
        binding.openOrdersList.layoutManager = LinearLayoutManager(this)
        binding.openOrdersList.adapter = receiptAdapter

        setupOrderTypeSpinner()
        setupTablePicker()
        setupModeToggle()
        setupPaymentMethodToggle()
        setupActions()
        setupSearch()
        updateReceiptModeVisibility()

        loadCatalog()
        setPosMode(PosMode.ORDER)
        requestBluetoothIfNeeded()
    }

    override fun onDestroy() {
        refreshJob?.cancel()
        tablePickerDialog?.dismiss()
        dayEndDialog?.dismiss()
        expenseDialog?.dismiss()
        stockTakeDialog?.dismiss()
        customerPaymentDialog?.dismiss()
        super.onDestroy()
    }

    private fun todayIso(): String {
        return SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date())
    }

    private fun openExpenseDialog() {
        lifecycleScope.launch {
            binding.refreshProgress.visibility = View.VISIBLE
            try {
                if (suppliers.isEmpty()) {
                    suppliers = withContext(Dispatchers.IO) { api.fetchSuppliers() }
                }
                showExpenseDialog()
            } catch (err: ApiException) {
                if (err.statusCode == 403) {
                    showExpenseDialog()
                } else {
                    handleApiError(err)
                }
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message ?: ""))
            } finally {
                binding.refreshProgress.visibility = View.GONE
            }
        }
    }

    private fun showExpenseDialog() {
        val dialogBinding = DialogExpenseBinding.inflate(layoutInflater)
        dialogBinding.expenseDateInput.setText(todayIso())

        val activeSuppliers = suppliers.filter { it.is_active }
        val supplierLabels = mutableListOf(getString(R.string.expense_supplier_none))
        supplierLabels.addAll(activeSuppliers.map { it.name })
        dialogBinding.expenseSupplierSpinner.adapter = ArrayAdapter(
            this,
            android.R.layout.simple_spinner_dropdown_item,
            supplierLabels,
        )

        val expenseCurrencies = allCurrencies.filter { it.is_active }
        val currencyLabels = expenseCurrencies.map { currency ->
            val symbol = currency.symbol.takeIf { it.isNotBlank() }?.let { " ($it)" }.orEmpty()
            "${currency.name}$symbol"
        }
        dialogBinding.expenseCurrencySpinner.adapter = ArrayAdapter(
            this,
            android.R.layout.simple_spinner_dropdown_item,
            currencyLabels,
        )
        val baseCurrencyIndex = expenseCurrencies.indexOfFirst { it.is_base }.takeIf { it >= 0 } ?: 0
        if (expenseCurrencies.isNotEmpty()) {
            dialogBinding.expenseCurrencySpinner.setSelection(baseCurrencyIndex)
        }

        expenseDialog = MaterialAlertDialogBuilder(this)
            .setTitle(R.string.expense_title)
            .setView(dialogBinding.root)
            .setNegativeButton(android.R.string.cancel, null)
            .setPositiveButton(R.string.save, null)
            .create()

        expenseDialog?.setOnShowListener {
            val saveButton = expenseDialog?.getButton(androidx.appcompat.app.AlertDialog.BUTTON_POSITIVE)
            saveButton?.setOnClickListener {
                saveExpense(
                    dialogBinding = dialogBinding,
                    expenseCurrencies = expenseCurrencies,
                    activeSuppliers = activeSuppliers,
                )
            }
        }
        expenseDialog?.show()
    }

    private fun saveExpense(
        dialogBinding: DialogExpenseBinding,
        expenseCurrencies: List<Currency>,
        activeSuppliers: List<Supplier>,
    ) {
        val description = dialogBinding.expenseDescriptionInput.text?.toString()?.trim().orEmpty()
        val amountRaw = dialogBinding.expenseAmountInput.text?.toString()?.trim().orEmpty()
        val expenseDate = dialogBinding.expenseDateInput.text?.toString()?.trim().orEmpty().ifBlank { todayIso() }
        val currencyIndex = dialogBinding.expenseCurrencySpinner.selectedItemPosition
        val currency = expenseCurrencies.getOrNull(currencyIndex)

        if (description.isBlank()) {
            dialogBinding.expenseDescriptionInput.error = getString(R.string.expense_description_required)
            dialogBinding.expenseDescriptionInput.requestFocus()
            return
        }
        val amount = amountRaw.toDoubleOrNull()
        if (amount == null || amount <= 0.0) {
            dialogBinding.expenseAmountInput.error = getString(R.string.expense_amount_required)
            dialogBinding.expenseAmountInput.requestFocus()
            return
        }
        if (currency == null) {
            Toast.makeText(this, R.string.expense_currency_required, Toast.LENGTH_SHORT).show()
            return
        }

        val supplierIndex = dialogBinding.expenseSupplierSpinner.selectedItemPosition - 1
        val supplierId = activeSuppliers.getOrNull(supplierIndex)?.id

        lifecycleScope.launch {
            binding.refreshProgress.visibility = View.VISIBLE
            try {
                withContext(Dispatchers.IO) {
                    api.createExpense(
                        expenseDate = expenseDate,
                        description = description,
                        amount = amountRaw,
                        currencyId = currency.id,
                        supplierId = supplierId,
                    )
                }
                expenseDialog?.dismiss()
                Toast.makeText(this@PosActivity, R.string.expense_recorded, Toast.LENGTH_SHORT).show()
            } catch (err: ApiException) {
                handleApiError(err)
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message ?: ""))
            } finally {
                binding.refreshProgress.visibility = View.GONE
            }
        }
    }

    private fun openStockTakeDialog() {
        lifecycleScope.launch {
            binding.refreshProgress.visibility = View.VISIBLE
            try {
                showStockTakeDialog()
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message ?: ""))
            } finally {
                binding.refreshProgress.visibility = View.GONE
            }
        }
    }

    private fun showStockTakeDialog() {
        val dialogBinding = DialogStockTakeBinding.inflate(layoutInflater)
        dialogBinding.stockTakeDateInput.setText(todayIso())
        val types = listOf(
            getString(R.string.stock_take_type_daily) to "daily",
            getString(R.string.stock_take_type_monthly) to "monthly",
        )
        dialogBinding.stockTakeTypeSpinner.adapter = ArrayAdapter(
            this,
            android.R.layout.simple_spinner_dropdown_item,
            types.map { it.first },
        )
        activeStockTake = null
        stockTakeLineInputs.clear()
        dialogBinding.stockTakeLines.removeAllViews()
        dialogBinding.stockTakeStatusLabel.text = getString(R.string.stock_take_start_hint)
        dialogBinding.stockTakeStartButton.visibility = View.VISIBLE

        fun selectedType(): String {
            val index = dialogBinding.stockTakeTypeSpinner.selectedItemPosition.coerceAtLeast(0)
            return types.getOrNull(index)?.second ?: "daily"
        }

        fun selectedDate(): String {
            return dialogBinding.stockTakeDateInput.text?.toString()?.trim().orEmpty().ifBlank { todayIso() }
        }

        fun periodDate(type: String, date: String): String {
            return if (type == "monthly" && date.length >= 7) "${date.take(7)}-01" else date
        }

        fun renderStockTake(stockTake: StockTake) {
            activeStockTake = stockTake
            dialogBinding.stockTakeStatusLabel.text =
                "${stockTake.stockTakeTypeDisplay} · ${stockTake.countDate}"
            dialogBinding.stockTakeStartButton.visibility = View.GONE
            dialogBinding.stockTakeLines.removeAllViews()
            stockTakeLineInputs.clear()
            if (stockTake.lines.isEmpty()) {
                dialogBinding.stockTakeLines.addView(
                    TextView(this).apply {
                        text = getString(R.string.stock_take_no_lines)
                        setTextColor(getColor(R.color.text_muted))
                        textSize = 13f
                    },
                )
                return
            }
            for (line in stockTake.lines) {
                val label = TextView(this).apply {
                    text = buildString {
                        append(line.productName)
                        if (!line.categoryName.isNullOrBlank()) {
                            append(" · ")
                            append(line.categoryName)
                        }
                    }
                    setTextColor(getColor(R.color.text_primary))
                    textSize = 14f
                    setPadding(0, 8, 0, 4)
                }
                val field = TextInputLayout(this).apply {
                    hint = getString(R.string.stock_take_counted)
                    layoutParams = LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT,
                        LinearLayout.LayoutParams.WRAP_CONTENT,
                    ).apply { bottomMargin = 8 }
                }
                val input = TextInputEditText(field.context).apply {
                    inputType = android.text.InputType.TYPE_CLASS_NUMBER or
                        android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL
                    setText(line.countedQuantity.orEmpty())
                }
                field.addView(input)
                dialogBinding.stockTakeLines.addView(label)
                dialogBinding.stockTakeLines.addView(field)
                stockTakeLineInputs[line.id] = input
            }
        }

        fun loadDraft() {
            lifecycleScope.launch {
                binding.refreshProgress.visibility = View.VISIBLE
                try {
                    val type = selectedType()
                    val date = periodDate(type, selectedDate())
                    val drafts = withContext(Dispatchers.IO) {
                        api.fetchStockTakes(type = type, status = "draft")
                    }
                    val draft = drafts.firstOrNull { it.countDate == date }
                    if (draft != null) {
                        val full = withContext(Dispatchers.IO) { api.fetchStockTake(draft.id) }
                        renderStockTake(full)
                    } else {
                        activeStockTake = null
                        stockTakeLineInputs.clear()
                        dialogBinding.stockTakeLines.removeAllViews()
                        dialogBinding.stockTakeStartButton.visibility = View.VISIBLE
                        dialogBinding.stockTakeStatusLabel.text =
                            getString(R.string.stock_take_start_hint)
                    }
                } catch (err: ApiException) {
                    handleApiError(err)
                } catch (err: Exception) {
                    showError(getString(R.string.connection_failed, err.message ?: ""))
                } finally {
                    binding.refreshProgress.visibility = View.GONE
                }
            }
        }

        dialogBinding.stockTakeStartButton.setOnClickListener {
            lifecycleScope.launch {
                binding.refreshProgress.visibility = View.VISIBLE
                try {
                    val created = withContext(Dispatchers.IO) {
                        api.createStockTake(selectedType(), selectedDate())
                    }
                    renderStockTake(created)
                } catch (err: ApiException) {
                    handleApiError(err)
                } catch (err: Exception) {
                    showError(getString(R.string.connection_failed, err.message ?: ""))
                } finally {
                    binding.refreshProgress.visibility = View.GONE
                }
            }
        }

        dialogBinding.stockTakeTypeSpinner.onItemSelectedListener =
            object : AdapterView.OnItemSelectedListener {
                override fun onItemSelected(
                    parent: AdapterView<*>?,
                    view: View?,
                    position: Int,
                    id: Long,
                ) {
                    loadDraft()
                }

                override fun onNothingSelected(parent: AdapterView<*>?) = Unit
            }

        stockTakeDialog = MaterialAlertDialogBuilder(this)
            .setTitle(R.string.stock_take_title)
            .setView(dialogBinding.root)
            .setNeutralButton(R.string.stock_take_save, null)
            .setNegativeButton(android.R.string.cancel, null)
            .setPositiveButton(R.string.stock_take_complete, null)
            .create()

        stockTakeDialog?.setOnShowListener {
            stockTakeDialog?.getButton(androidx.appcompat.app.AlertDialog.BUTTON_NEUTRAL)
                ?.setOnClickListener { saveStockTake(complete = false) }
            stockTakeDialog?.getButton(androidx.appcompat.app.AlertDialog.BUTTON_POSITIVE)
                ?.setOnClickListener { saveStockTake(complete = true) }
        }
        stockTakeDialog?.show()
    }

    private fun collectStockTakeLines(): List<Pair<Int, String?>> {
        return stockTakeLineInputs.map { (lineId, input) ->
            val raw = input.text?.toString()?.trim().orEmpty()
            lineId to raw.ifBlank { null }
        }
    }

    private fun saveStockTake(complete: Boolean) {
        val stockTake = activeStockTake ?: run {
            Toast.makeText(this, R.string.stock_take_start_hint, Toast.LENGTH_SHORT).show()
            return
        }
        lifecycleScope.launch {
            binding.refreshProgress.visibility = View.VISIBLE
            try {
                val updated = withContext(Dispatchers.IO) {
                    api.updateStockTakeLines(stockTake.id, collectStockTakeLines())
                }
                if (complete) {
                    withContext(Dispatchers.IO) { api.completeStockTake(stockTake.id) }
                    stockTakeDialog?.dismiss()
                    activeStockTake = null
                    Toast.makeText(this@PosActivity, R.string.stock_take_completed, Toast.LENGTH_SHORT).show()
                } else {
                    activeStockTake = updated
                    Toast.makeText(this@PosActivity, R.string.stock_take_saved, Toast.LENGTH_SHORT).show()
                }
            } catch (err: ApiException) {
                handleApiError(err)
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message ?: ""))
            } finally {
                binding.refreshProgress.visibility = View.GONE
            }
        }
    }

    private fun openCustomerPaymentDialog() {
        lifecycleScope.launch {
            binding.refreshProgress.visibility = View.VISIBLE
            try {
                customers = withContext(Dispatchers.IO) { api.fetchCustomers() }
                if (allCurrencies.isEmpty()) {
                    allCurrencies = withContext(Dispatchers.IO) { api.fetchCurrencies() }
                }
                if (customers.isEmpty()) {
                    Toast.makeText(
                        this@PosActivity,
                        R.string.customer_payment_no_customers,
                        Toast.LENGTH_LONG,
                    ).show()
                    return@launch
                }
                showCustomerPaymentDialog()
            } catch (err: ApiException) {
                handleApiError(err)
                Toast.makeText(this@PosActivity, err.message, Toast.LENGTH_LONG).show()
            } catch (err: Exception) {
                val message = getString(R.string.connection_failed, err.message ?: "")
                showError(message)
                Toast.makeText(this@PosActivity, message, Toast.LENGTH_LONG).show()
            } finally {
                binding.refreshProgress.visibility = View.GONE
            }
        }
    }

    private fun showCustomerPaymentDialog() {
        val dialogBinding = DialogCustomerPaymentBinding.inflate(layoutInflater)
        val labels = mutableListOf(getString(R.string.customer_payment_select_hint))
        labels.addAll(customers.map { it.full_name })
        dialogBinding.customerPaymentCustomerSpinner.adapter = ArrayAdapter(
            this,
            android.R.layout.simple_spinner_dropdown_item,
            labels,
        )

        val paymentCurrencies = allCurrencies.filter { it.is_active }.ifEmpty { allCurrencies }
        if (paymentCurrencies.isEmpty()) {
            Toast.makeText(this, R.string.customer_payment_currency_required, Toast.LENGTH_LONG).show()
            return
        }
        dialogBinding.customerPaymentCurrencySpinner.adapter = ArrayAdapter(
            this,
            android.R.layout.simple_spinner_dropdown_item,
            paymentCurrencies.map { currency ->
                val symbol = currency.symbol.takeIf { it.isNotBlank() }?.let { " ($it)" }.orEmpty()
                "${currency.name.ifBlank { currency.code }}$symbol"
            },
        )
        val baseIndex = paymentCurrencies.indexOfFirst { it.is_base }.takeIf { it >= 0 } ?: 0
        dialogBinding.customerPaymentCurrencySpinner.setSelection(baseIndex)

        fun updateBalance() {
            val index = dialogBinding.customerPaymentCustomerSpinner.selectedItemPosition - 1
            val customer = customers.getOrNull(index)
            dialogBinding.customerPaymentBalanceLabel.text = if (customer == null) {
                getString(R.string.customer_payment_select_hint)
            } else {
                getString(
                    R.string.customer_payment_balance,
                    ProductAdapter.formatMoney(customer.account_balance),
                )
            }
        }

        dialogBinding.customerPaymentCustomerSpinner.onItemSelectedListener =
            object : AdapterView.OnItemSelectedListener {
                override fun onItemSelected(
                    parent: AdapterView<*>?,
                    view: View?,
                    position: Int,
                    id: Long,
                ) {
                    updateBalance()
                }

                override fun onNothingSelected(parent: AdapterView<*>?) = Unit
            }
        updateBalance()

        customerPaymentDialog = MaterialAlertDialogBuilder(this)
            .setTitle(R.string.customer_payment_title)
            .setView(dialogBinding.root)
            .setNegativeButton(android.R.string.cancel, null)
            .setPositiveButton(R.string.customer_payment_record, null)
            .create()

        customerPaymentDialog?.setOnShowListener {
            customerPaymentDialog?.getButton(androidx.appcompat.app.AlertDialog.BUTTON_POSITIVE)
                ?.setOnClickListener {
                    saveCustomerPayment(dialogBinding, paymentCurrencies)
                }
        }
        customerPaymentDialog?.show()
    }

    private fun parseDepositAmount(raw: String): Double? {
        val normalized = raw.trim().replace(',', '.')
        return normalized.toDoubleOrNull()
    }

    private fun saveCustomerPayment(
        dialogBinding: DialogCustomerPaymentBinding,
        paymentCurrencies: List<Currency>,
    ) {
        val customerIndex = dialogBinding.customerPaymentCustomerSpinner.selectedItemPosition - 1
        val customer = customers.getOrNull(customerIndex)
        val amountRaw = dialogBinding.customerPaymentAmountInput.text?.toString()?.trim().orEmpty()
        val currency = paymentCurrencies.getOrNull(
            dialogBinding.customerPaymentCurrencySpinner.selectedItemPosition,
        )
        val notes = dialogBinding.customerPaymentNotesInput.text?.toString()?.trim().orEmpty()

        if (customer == null) {
            Toast.makeText(this, R.string.customer_payment_customer_required, Toast.LENGTH_SHORT).show()
            return
        }
        val amount = parseDepositAmount(amountRaw)
        if (amount == null || amount <= 0.0) {
            dialogBinding.customerPaymentAmountInput.error =
                getString(R.string.customer_payment_amount_required)
            dialogBinding.customerPaymentAmountInput.requestFocus()
            return
        }
        if (currency == null) {
            Toast.makeText(this, R.string.customer_payment_currency_required, Toast.LENGTH_SHORT).show()
            return
        }
        if (session.branchId <= 0) {
            Toast.makeText(this, R.string.customer_payment_branch_required, Toast.LENGTH_LONG).show()
            return
        }

        val saveButton = customerPaymentDialog
            ?.getButton(androidx.appcompat.app.AlertDialog.BUTTON_POSITIVE)
        saveButton?.isEnabled = false

        lifecycleScope.launch {
            binding.refreshProgress.visibility = View.VISIBLE
            try {
                val result = withContext(Dispatchers.IO) {
                    val deposited = api.depositToCustomer(
                        customerId = customer.id,
                        currencyId = currency.id,
                        amount = String.format(Locale.US, "%.2f", amount),
                        notes = notes,
                    )
                    // Confirm against the portal API — never trust a redirect/false success.
                    val confirmed = api.fetchCustomer(customer.id)
                    deposited to confirmed
                }
                val (deposited, confirmed) = result
                customers = customers.map {
                    if (it.id == customer.id) {
                        it.copy(account_balance = confirmed.account_balance)
                    } else {
                        it
                    }
                }
                setupCustomerSpinner(customer.id)
                updateAccountBalanceHint()
                customerPaymentDialog?.dismiss()
                Toast.makeText(
                    this@PosActivity,
                    getString(
                        R.string.customer_payment_recorded_balance,
                        ProductAdapter.formatMoney(confirmed.account_balance),
                    ) + " (#${deposited.transactionId})",
                    Toast.LENGTH_LONG,
                ).show()
            } catch (err: ApiException) {
                handleApiError(err)
                Toast.makeText(this@PosActivity, err.message, Toast.LENGTH_LONG).show()
                saveButton?.isEnabled = true
            } catch (err: Exception) {
                val message = getString(R.string.connection_failed, err.message ?: "")
                showError(message)
                Toast.makeText(this@PosActivity, message, Toast.LENGTH_LONG).show()
                saveButton?.isEnabled = true
            } finally {
                binding.refreshProgress.visibility = View.GONE
            }
        }
    }

    private fun openDayEndDialog() {
        lifecycleScope.launch {
            binding.refreshProgress.visibility = View.VISIBLE
            try {
                val date = todayIso()
                val check = withContext(Dispatchers.IO) { api.checkDayEndStockTake(date) }
                if (!check.completed) {
                    MaterialAlertDialogBuilder(this@PosActivity)
                        .setTitle(R.string.day_end_stock_take_required)
                        .setMessage(check.detail)
                        .setNegativeButton(android.R.string.cancel, null)
                        .setPositiveButton(R.string.stock_take_open) { _, _ ->
                            openStockTakeDialog()
                        }
                        .show()
                    return@launch
                }
                showDayEndDialog(date)
            } catch (err: ApiException) {
                handleApiError(err)
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message ?: ""))
            } finally {
                binding.refreshProgress.visibility = View.GONE
            }
        }
    }

    private fun showDayEndDialog(initialDate: String) {
        val dialogBinding = DialogDayEndBinding.inflate(layoutInflater)
        dialogBinding.dayEndDateInput.setText(initialDate)
        dialogBinding.dayEndCurrencyFields.removeAllViews()

        val activeCurrencies = currencies.filter { it.is_active }
        val fiscal = session.fiscalizationEnabled
        val codes = activeCurrencies
            .map { it.code.trim().uppercase() }
            .filter { it.isNotBlank() }
            .distinct()
            .sorted()

        val countedInputs = linkedMapOf<Int, TextInputEditText>()
        var selectedCode = codes.firstOrNull().orEmpty()
        if (fiscal && codes.isNotEmpty()) {
            val codeSpinner = android.widget.Spinner(this)
            codeSpinner.adapter = android.widget.ArrayAdapter(
                this,
                android.R.layout.simple_spinner_dropdown_item,
                codes,
            )
            dialogBinding.dayEndCurrencyFields.addView(
                android.widget.TextView(this).apply {
                    text = getString(R.string.day_end_currency_code)
                    setTextColor(getColor(R.color.text_muted))
                    textSize = 13f
                    setPadding(0, 0, 0, 8)
                },
            )
            dialogBinding.dayEndCurrencyFields.addView(
                codeSpinner,
                android.widget.LinearLayout.LayoutParams(
                    android.widget.LinearLayout.LayoutParams.MATCH_PARENT,
                    android.widget.LinearLayout.LayoutParams.WRAP_CONTENT,
                ).apply { bottomMargin = 12 },
            )
            codeSpinner.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
                override fun onItemSelected(
                    parent: android.widget.AdapterView<*>?,
                    view: android.view.View?,
                    position: Int,
                    id: Long,
                ) {
                    selectedCode = codes[position]
                    rebuildDayEndCurrencyInputs(
                        dialogBinding,
                        activeCurrencies,
                        countedInputs,
                        selectedCode = selectedCode,
                        fiscal = true,
                    )
                }

                override fun onNothingSelected(parent: android.widget.AdapterView<*>?) = Unit
            }
        }

        rebuildDayEndCurrencyInputs(
            dialogBinding,
            activeCurrencies,
            countedInputs,
            selectedCode = selectedCode,
            fiscal = fiscal,
        )

        dayEndDialog = MaterialAlertDialogBuilder(this)
            .setTitle(R.string.day_end_title)
            .setView(dialogBinding.root)
            .setNegativeButton(android.R.string.cancel, null)
            .setPositiveButton(R.string.day_end_print, null)
            .create()

        dayEndDialog?.setOnShowListener {
            dayEndDialog?.getButton(androidx.appcompat.app.AlertDialog.BUTTON_POSITIVE)?.setOnClickListener {
                printDayEndReport(dialogBinding, countedInputs)
            }
        }
        dayEndDialog?.show()
    }

    private fun rebuildDayEndCurrencyInputs(
        dialogBinding: DialogDayEndBinding,
        activeCurrencies: List<Currency>,
        countedInputs: MutableMap<Int, TextInputEditText>,
        selectedCode: String,
        fiscal: Boolean,
    ) {
        // Keep the code spinner (first two children when fiscal); clear currency inputs after.
        val keepPrefix = if (fiscal && selectedCode.isNotBlank()) 2 else 0
        while (dialogBinding.dayEndCurrencyFields.childCount > keepPrefix) {
            dialogBinding.dayEndCurrencyFields.removeViewAt(dialogBinding.dayEndCurrencyFields.childCount - 1)
        }
        countedInputs.clear()

        val visible = if (fiscal && selectedCode.isNotBlank()) {
            activeCurrencies.filter { it.code.trim().uppercase() == selectedCode }
        } else {
            activeCurrencies
        }

        for (currency in visible) {
            val label = currency.name.ifBlank { currency.code }
            val fieldLayout = TextInputLayout(this).apply {
                hint = label
                layoutParams = android.widget.LinearLayout.LayoutParams(
                    android.widget.LinearLayout.LayoutParams.MATCH_PARENT,
                    android.widget.LinearLayout.LayoutParams.WRAP_CONTENT,
                ).apply { bottomMargin = 12 }
            }
            val input = TextInputEditText(fieldLayout.context).apply {
                inputType = android.text.InputType.TYPE_CLASS_NUMBER or
                    android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL
                tag = currency.code.trim().uppercase()
            }
            fieldLayout.addView(input)
            dialogBinding.dayEndCurrencyFields.addView(fieldLayout)
            countedInputs[currency.id] = input
        }
    }

    private fun printDayEndReport(
        dialogBinding: DialogDayEndBinding,
        countedInputs: Map<Int, TextInputEditText>,
    ) {
        val reportDate = dialogBinding.dayEndDateInput.text?.toString()?.trim().orEmpty()
            .ifBlank { todayIso() }
        val counted = linkedMapOf<Int, String>()
        val countedCodes = linkedSetOf<String>()
        for ((currencyId, input) in countedInputs) {
            val raw = input.text?.toString()?.trim().orEmpty()
            if (raw.isBlank()) continue
            val amount = raw.toDoubleOrNull()
            if (amount == null || amount < 0) {
                val currency = currencies.firstOrNull { it.id == currencyId }
                Toast.makeText(
                    this,
                    getString(R.string.day_end_invalid_amount, currency?.name ?: "currency"),
                    Toast.LENGTH_SHORT,
                ).show()
                return
            }
            val code = (input.tag as? String).orEmpty()
            if (code.isNotBlank()) countedCodes.add(code)
            counted[currencyId] = String.format(Locale.US, "%.2f", amount)
        }
        if (session.fiscalizationEnabled && countedCodes.size > 1) {
            Toast.makeText(this, R.string.day_end_mixed_codes, Toast.LENGTH_LONG).show()
            return
        }

        lifecycleScope.launch {
            binding.refreshProgress.visibility = View.VISIBLE
            try {
                val check = withContext(Dispatchers.IO) { api.checkDayEndStockTake(reportDate) }
                if (!check.completed) {
                    MaterialAlertDialogBuilder(this@PosActivity)
                        .setTitle(R.string.day_end_stock_take_required)
                        .setMessage(check.detail)
                        .setNegativeButton(android.R.string.cancel, null)
                        .setPositiveButton(R.string.stock_take_open) { _, _ ->
                            openStockTakeDialog()
                        }
                        .show()
                    return@launch
                }
                val report = withContext(Dispatchers.IO) {
                    api.fetchDayEndReport(reportDate, counted)
                }
                printDayEnd(report)
                dayEndDialog?.dismiss()
                Toast.makeText(this@PosActivity, R.string.day_end_printed, Toast.LENGTH_LONG).show()
            } catch (err: ApiException) {
                if (err.statusCode == 403) {
                    MaterialAlertDialogBuilder(this@PosActivity)
                        .setTitle(R.string.day_end_stock_take_required)
                        .setMessage(err.message ?: getString(R.string.day_end_stock_take_required))
                        .setNegativeButton(android.R.string.cancel, null)
                        .setPositiveButton(R.string.stock_take_open) { _, _ ->
                            openStockTakeDialog()
                        }
                        .show()
                } else {
                    handleApiError(err)
                }
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message ?: ""))
            } finally {
                binding.refreshProgress.visibility = View.GONE
            }
        }
    }

    private suspend fun printDayEnd(report: com.cafedeparis.kitchen.data.DayEndReportResponse) {
        val printerAddress = session.printerAddress
        if (printerAddress.isNullOrBlank()) {
            withContext(Dispatchers.Main) {
                Toast.makeText(this@PosActivity, R.string.printer_not_configured, Toast.LENGTH_SHORT).show()
            }
            return
        }
        try {
            withContext(Dispatchers.IO) {
                printer.printDayEnd(printerAddress, report)
            }
        } catch (err: PrinterException) {
            withContext(Dispatchers.Main) {
                showError(getString(R.string.print_failed, err.message ?: ""))
            }
        } catch (err: SecurityException) {
            withContext(Dispatchers.Main) {
                requestBluetoothIfNeeded()
                showError(getString(R.string.bluetooth_permission_required))
            }
        } catch (err: Exception) {
            withContext(Dispatchers.Main) {
                showError(getString(R.string.print_failed, err.message ?: ""))
            }
        }
    }

    private fun setupOrderTypeSpinner() {
        val types = listOf(
            getString(R.string.order_type_takeaway) to "takeaway",
            getString(R.string.order_type_dine_in) to "dine_in",
        )
        val labels = types.map { it.first }
        val adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, labels)
        binding.orderTypeSpinner.adapter = adapter
        binding.orderTypeSpinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                syncOrderTypeUi(types[position].second)
            }

            override fun onNothingSelected(parent: AdapterView<*>?) = Unit
        }
        syncOrderTypeUi(types[binding.orderTypeSpinner.selectedItemPosition].second)
    }

    private fun setupTablePicker() {
        binding.tableSelectButton.setOnClickListener { openTablePicker() }
    }

    private fun syncOrderTypeUi(orderType: String) {
        val isDineIn = orderType == "dine_in"
        binding.tableSelectButton.visibility =
            if (isDineIn && posMode == PosMode.ORDER) View.VISIBLE else View.GONE
        if (!isDineIn) {
            setSelectedTable(null)
        }
    }

    private fun setSelectedTable(name: String?) {
        selectedTableName = name?.trim()?.takeIf { it.isNotEmpty() }
        binding.tableSelectButton.text = selectedTableName ?: getString(R.string.choose_table)
    }

    private fun occupiedTableNames(orders: List<KitchenOrder>): Set<String> {
        return orders.filter { order ->
            order.order_type == "dine_in" && order.table_number.isNotBlank()
        }.map { it.table_number }.toSet()
    }

    private fun openOrdersForTable(tableNumber: String): List<KitchenOrder> {
        val table = tableNumber.trim()
        if (table.isEmpty()) return emptyList()
        return openOrders.filter { it.order_type == "dine_in" && it.table_number == table }
    }

    private fun receiptOrders(): List<KitchenOrder> {
        val order = selectedOrder ?: return emptyList()
        val tableOrders = openOrdersForTable(order.table_number)
        return if (tableOrders.size > 1) tableOrders else listOf(order)
    }

    private fun receiptInclusiveTotal(): Double {
        return receiptOrders().sumOf { it.total_amount.toDoubleOrNull() ?: 0.0 }
    }

    private fun openTablePicker() {
        lifecycleScope.launch {
            binding.refreshProgress.visibility = View.VISIBLE
            try {
                val (tables, orders) = withContext(Dispatchers.IO) {
                    Pair(api.fetchDiningTables(), api.fetchOpenOrders())
                }
                diningTables = tables.filter { it.is_active }.sortedBy { it.sort_order }
                openOrders = orders
                showTablePickerDialog(diningTables, occupiedTableNames(orders))
            } catch (err: ApiException) {
                handleApiError(err)
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message ?: ""))
            } finally {
                binding.refreshProgress.visibility = View.GONE
            }
        }
    }

    private fun showTablePickerDialog(tables: List<DiningTable>, occupied: Set<String>) {
        val dialogBinding = DialogTablePickerBinding.inflate(layoutInflater)
        val adapter = DiningTableAdapter(
            occupiedNames = occupied,
            selectedName = selectedTableName,
            onTableClick = { table ->
                setSelectedTable(table.name)
                tablePickerDialog?.dismiss()
            },
        )
        dialogBinding.tableGrid.layoutManager = GridLayoutManager(this, 3)
        dialogBinding.tableGrid.adapter = adapter
        adapter.submitList(tables)

        val hasTables = tables.isNotEmpty()
        dialogBinding.tableGrid.visibility = if (hasTables) View.VISIBLE else View.GONE
        dialogBinding.tableEmptyLabel.visibility = if (hasTables) View.GONE else View.VISIBLE
        if (!hasTables) {
            dialogBinding.tableEmptyLabel.text = if (session.canManageDiningTables) {
                getString(R.string.no_tables_configured_manager)
            } else {
                getString(R.string.no_tables_configured)
            }
        }

        tablePickerDialog = MaterialAlertDialogBuilder(this)
            .setTitle(R.string.select_table_title)
            .setView(dialogBinding.root)
            .setNegativeButton(android.R.string.cancel, null)
            .create()
        tablePickerDialog?.show()
    }

    private fun setupModeToggle() {
        binding.modeToggle.check(binding.orderModeButton.id)
        binding.modeToggle.addOnButtonCheckedListener { _, checkedId, isChecked ->
            if (!isChecked) return@addOnButtonCheckedListener
            if (checkedId == binding.receiptModeButton.id && !session.canCollectPayment) {
                binding.modeToggle.check(binding.orderModeButton.id)
                return@addOnButtonCheckedListener
            }
            setPosMode(if (checkedId == binding.receiptModeButton.id) PosMode.RECEIPT else PosMode.ORDER)
        }
    }

    private fun updateReceiptModeVisibility() {
        val showReceipt = session.canCollectPayment
        binding.receiptModeButton.visibility = if (showReceipt) View.VISIBLE else View.GONE
        binding.stockTakeButton.visibility = if (showReceipt) View.VISIBLE else View.GONE
        binding.customerPaymentButton.visibility = if (showReceipt) View.VISIBLE else View.GONE
        if (!showReceipt && posMode == PosMode.RECEIPT) {
            setPosMode(PosMode.ORDER)
        }
    }

    private fun setupPaymentMethodToggle() {
        binding.paymentMethodToggle.check(binding.cashPaymentButton.id)
        binding.paymentMethodToggle.addOnButtonCheckedListener { _, checkedId, isChecked ->
            if (!isChecked) return@addOnButtonCheckedListener
            paymentMethod = if (checkedId == binding.accountPaymentButton.id) {
                PaymentMethod.ACCOUNT
            } else {
                PaymentMethod.CASH
            }
            syncPaymentMethodUi()
            updateReceiptCheckoutState()
        }
        binding.customerSpinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                updateAccountBalanceHint()
                updateReceiptCheckoutState()
                linkSelectedCustomerToOrder()
            }

            override fun onNothingSelected(parent: AdapterView<*>?) = Unit
        }
        val splitWatcher = object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) = Unit
            override fun afterTextChanged(s: Editable?) {
                updateSplitPaymentRemaining()
                updateReceiptCheckoutState()
            }
        }
        binding.splitPaymentEnabled.setOnCheckedChangeListener { _, isChecked ->
            binding.splitPaymentFields.visibility = if (isChecked) View.VISIBLE else View.GONE
            binding.currencyGroup.visibility = if (isChecked || paymentMethod == PaymentMethod.ACCOUNT) {
                View.GONE
            } else {
                View.VISIBLE
            }
            if (!isChecked) {
                clearSplitPaymentInputs()
            } else {
                renderSplitPaymentRows(splitWatcher)
                updateSplitPaymentRemaining()
            }
            updateReceiptCheckoutState()
        }
        binding.splitFillCashButton.setOnClickListener {
            if (!isSplitPaymentActive()) return@setOnClickListener
            val orderTotal = receiptInclusiveTotal()
            val target = currencies.firstOrNull { it.is_base && paymentRate(it) != null }
                ?: usableCurrencies().firstOrNull { paymentRate(it) != null }
                ?: return@setOnClickListener
            val othersBase = splitPaymentLines()
                .filter { it.first != target.id }
                .sumOf { it.third }
            val restBase = roundMoney(orderTotal - othersBase)
            val rate = paymentRate(target) ?: return@setOnClickListener
            val rest = roundMoney(restBase * rate)
            val input = binding.splitPaymentRows.findViewWithTag<EditText>("split-${target.id}")
            input?.setText(if (rest > 0) String.format("%.2f", rest) else "")
            updateSplitPaymentRemaining()
            updateReceiptCheckoutState()
        }
    }

    private fun allowsSplitPayment(): Boolean = !session.fiscalizationEnabled

    private fun isSplitPaymentActive(): Boolean {
        return allowsSplitPayment()
            && paymentMethod != PaymentMethod.ACCOUNT
            && binding.splitPaymentEnabled.isChecked
    }

    private fun renderSplitPaymentRows(watcher: TextWatcher) {
        binding.splitPaymentRows.removeAllViews()
        usableCurrencies().forEach { currency ->
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = android.view.Gravity.CENTER_VERTICAL
                layoutParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                ).also { it.bottomMargin = (4 * resources.displayMetrics.density).toInt() }
            }
            val label = TextView(this).apply {
                layoutParams = LinearLayout.LayoutParams(
                    (96 * resources.displayMetrics.density).toInt(),
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                )
                text = currency.name
                setTextColor(ContextCompat.getColor(this@PosActivity, R.color.text_muted))
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            }
            val input = EditText(this).apply {
                tag = "split-${currency.id}"
                layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
                hint = splitPaymentPlaceholder(currency)
                inputType = android.text.InputType.TYPE_CLASS_NUMBER or
                    android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL
                maxLines = 1
                addTextChangedListener(watcher)
            }
            row.addView(label)
            row.addView(input)
            binding.splitPaymentRows.addView(row)
        }
    }

    private fun clearSplitPaymentInputs() {
        for (i in 0 until binding.splitPaymentRows.childCount) {
            val row = binding.splitPaymentRows.getChildAt(i) as? LinearLayout ?: continue
            (row.getChildAt(1) as? EditText)?.setText("")
        }
        updateSplitPaymentRemaining()
    }

    /** Triple(currencyId, amountInCurrency, amountInBase) */
    private fun splitPaymentLines(): List<Triple<Int, Double, Double>> {
        if (!isSplitPaymentActive()) return emptyList()
        return usableCurrencies().mapNotNull { currency ->
            val input = binding.splitPaymentRows.findViewWithTag<EditText>("split-${currency.id}")
            val amount = input?.text?.toString()?.toDoubleOrNull() ?: 0.0
            val rate = paymentRate(currency) ?: return@mapNotNull null
            if (amount <= 0) return@mapNotNull null
            val rounded = roundMoney(amount)
            Triple(currency.id, rounded, roundMoney(rounded / rate))
        }
    }

    private fun splitPaymentRemainingBase(excludeCurrencyId: Int? = null): Double? {
        if (!isSplitPaymentActive()) return null
        val orderTotal = receiptInclusiveTotal()
        val othersBase = splitPaymentLines()
            .filter { it.first != excludeCurrencyId }
            .sumOf { it.third }
        return roundMoney(orderTotal - othersBase)
    }

    private fun splitPaymentPlaceholder(currency: Currency): String {
        val remainingBase = splitPaymentRemainingBase(currency.id) ?: return "0.00"
        val rate = paymentRate(currency) ?: return "0.00"
        val amount = roundMoney(remainingBase * rate)
        return if (amount > 0) String.format(Locale.US, "%.2f", amount) else "0.00"
    }

    private fun updateSplitPaymentPlaceholders() {
        if (!isSplitPaymentActive()) return
        usableCurrencies().forEach { currency ->
            val input = binding.splitPaymentRows.findViewWithTag<EditText>("split-${currency.id}")
                ?: return@forEach
            input.hint = splitPaymentPlaceholder(currency)
        }
    }

    private fun updateSplitPaymentRemaining() {
        if (!isSplitPaymentActive()) return
        val orderTotal = receiptInclusiveTotal()
        val allocated = splitPaymentLines().sumOf { it.third }
        val remaining = roundMoney(orderTotal - allocated)
        binding.splitRemainingLabel.text = if (remaining < -0.005) {
            getString(
                R.string.split_change,
                ProductAdapter.formatMoney(-remaining, baseCurrencySymbol()),
            )
        } else {
            getString(
                R.string.split_remaining,
                ProductAdapter.formatMoney(remaining, baseCurrencySymbol()),
            )
        }
        updateSplitPaymentPlaceholders()
    }

    private fun syncPaymentMethodUi() {
        val isAccount = paymentMethod == PaymentMethod.ACCOUNT
        binding.customerGroup.visibility = if (isAccount) View.VISIBLE else View.GONE
        val available = !isAccount && allowsSplitPayment()
        binding.splitPaymentGroup.visibility = if (available) View.VISIBLE else View.GONE
        if (!available) {
            binding.splitPaymentEnabled.isChecked = false
            binding.splitPaymentFields.visibility = View.GONE
            clearSplitPaymentInputs()
            binding.currencyGroup.visibility = if (isAccount) View.GONE else View.VISIBLE
        } else {
            val splitOn = binding.splitPaymentEnabled.isChecked
            binding.splitPaymentFields.visibility = if (splitOn) View.VISIBLE else View.GONE
            binding.currencyGroup.visibility = if (splitOn) View.GONE else View.VISIBLE
            if (splitOn) {
                updateSplitPaymentRemaining()
            }
        }
        updateAccountBalanceHint()
    }

    private fun setupCustomerSpinner(preselectCustomerId: Int? = null) {
        val labels = mutableListOf(getString(R.string.customer_walk_in))
        labels.addAll(customers.map(::customerLabel))
        val adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, labels)
        binding.customerSpinner.adapter = adapter
        val index = preselectCustomerId?.let { customerId ->
            customers.indexOfFirst { it.id == customerId }.takeIf { it >= 0 }?.plus(1)
        } ?: 0
        binding.customerSpinner.setSelection(index)
    }

    private fun customerLabel(customer: Customer): String {
        val limit = customer.credit_limit.toDoubleOrNull() ?: 0.0
        val limitSuffix = if (limit > 0) {
            " · Limit ${ProductAdapter.formatMoney(customer.credit_limit)}"
        } else {
            ""
        }
        return customer.full_name + limitSuffix
    }

    private fun selectedCustomer(): Customer? {
        val index = binding.customerSpinner.selectedItemPosition - 1
        return customers.getOrNull(index)
    }

    private fun updateAccountBalanceHint() {
        if (paymentMethod != PaymentMethod.ACCOUNT) {
            binding.accountBalanceHint.visibility = View.GONE
            return
        }
        val customer = selectedCustomer()
        if (customer == null) {
            binding.accountBalanceHint.visibility = View.GONE
            return
        }
        binding.accountBalanceHint.visibility = View.VISIBLE
        binding.accountBalanceHint.text = getString(
            R.string.account_balance_hint,
            ProductAdapter.formatMoney(customer.credit_limit, baseCurrencySymbol()),
        )
    }

    private fun linkSelectedCustomerToOrder() {
        val order = selectedOrder ?: return
        val customer = selectedCustomer()
        val customerId = customer?.id
        if (order.customer == customerId) return

        lifecycleScope.launch {
            try {
                val updated = withContext(Dispatchers.IO) {
                    api.updateOrderCustomer(order.id, customerId)
                }
                selectedOrder = updated
                val index = openOrders.indexOfFirst { it.id == updated.id }
                if (index >= 0) {
                    openOrders = openOrders.toMutableList().also { it[index] = updated }
                }
            } catch (err: ApiException) {
                handleApiError(err)
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message ?: ""))
            }
        }
    }

    private fun updateReceiptCheckoutState() {
        val order = selectedOrder ?: return
        val total = receiptInclusiveTotal()
        updatePaymentTotalDisplay(total)
        binding.checkoutButton.isEnabled = when (paymentMethod) {
            PaymentMethod.ACCOUNT -> {
                val customer = selectedCustomer()
                customer != null && customer.availableCredit() >= total
            }
            PaymentMethod.CASH -> {
                if (isSplitPaymentActive()) {
                    val lines = splitPaymentLines()
                    val allocated = lines.sumOf { it.third }
                    lines.isNotEmpty() && allocated + 0.005 >= total
                } else {
                    val currency = selectedCurrency()
                    currency != null && paymentRate(currency) != null
                }
            }
        }
        val combined = receiptOrders().size > 1
        binding.checkoutButton.text = getString(
            if (combined) R.string.collect_table_payment else R.string.collect_payment,
        )
    }

    private fun paymentRate(currency: Currency): Double? {
        if (currency.is_base) return 1.0
        val rate = currency.current_rate?.toDoubleOrNull()
        return rate?.takeIf { it > 0.0 }
    }

    private fun roundMoney(amount: Double): Double {
        return kotlin.math.round(amount * 100.0) / 100.0
    }

    private fun baseCurrencySymbol(): String? {
        return currencies.firstOrNull { it.is_base }?.symbol?.takeIf { it.isNotBlank() }
    }

    private fun updatePaymentTotalDisplay(baseTotal: Double) {
        if (posMode != PosMode.RECEIPT || paymentMethod == PaymentMethod.ACCOUNT || isSplitPaymentActive()) {
            binding.totalCaption.setText(R.string.total)
            binding.totalLabel.text = ProductAdapter.formatMoney(baseTotal, baseCurrencySymbol())
            binding.exchangeRateLabel.visibility = View.GONE
            updateSplitPaymentRemaining()
            return
        }
        val currency = selectedCurrency()
        val rate = currency?.let(::paymentRate)
        if (currency != null && rate != null) {
            val amountDue = roundMoney(baseTotal * rate)
            binding.totalCaption.setText(
                if (currency.is_base) R.string.total else R.string.amount_due,
            )
            binding.totalLabel.text = ProductAdapter.formatMoney(
                amountDue,
                currency.symbol.takeIf { it.isNotBlank() } ?: baseCurrencySymbol(),
            )
            if (!currency.is_base) {
                binding.exchangeRateLabel.text = getString(R.string.exchange_rate_label, rate.toString())
                binding.exchangeRateLabel.visibility = View.VISIBLE
            } else {
                binding.exchangeRateLabel.visibility = View.GONE
            }
            updateSplitPaymentRemaining()
        } else {
            binding.totalCaption.setText(R.string.total)
            binding.totalLabel.text = ProductAdapter.formatMoney(baseTotal, baseCurrencySymbol())
            binding.exchangeRateLabel.visibility = View.GONE
            updateSplitPaymentRemaining()
        }
    }

    private fun setupActions() {
        binding.logoutButton.setOnClickListener {
            refreshJob?.cancel()
            session.clearLogin()
            startActivity(Intent(this, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            })
            finish()
        }
        binding.settingsButton.setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }
        binding.expenseButton.setOnClickListener { openExpenseDialog() }
        binding.stockTakeButton.setOnClickListener { openStockTakeDialog() }
        binding.customerPaymentButton.setOnClickListener { openCustomerPaymentDialog() }
        binding.dayEndButton.setOnClickListener { openDayEndDialog() }
        binding.clearButton.setOnClickListener {
            if (posMode == PosMode.ORDER) {
                cart.clear()
                renderCart()
            }
        }
        binding.cancelOrderButton.setOnClickListener {
            cancelSelectedOrder()
        }
        binding.checkoutButton.setOnClickListener {
            if (posMode == PosMode.ORDER) {
                placeOrder()
            } else {
                paySelectedOrder()
            }
        }
    }

    private fun setupSearch() {
        binding.productSearchInput.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) = Unit
            override fun afterTextChanged(s: Editable?) {
                searchQuery = s?.toString()?.trim()?.lowercase().orEmpty()
                renderProducts()
            }
        })
    }

    private fun setPosMode(mode: PosMode) {
        val resolvedMode = if (mode == PosMode.RECEIPT && !session.canCollectPayment) {
            PosMode.ORDER
        } else {
            mode
        }
        posMode = resolvedMode
        binding.orderModePanel.visibility = if (resolvedMode == PosMode.ORDER) View.VISIBLE else View.GONE
        binding.receiptModePanel.visibility = if (resolvedMode == PosMode.RECEIPT) View.VISIBLE else View.GONE
        binding.paymentSection.visibility = if (resolvedMode == PosMode.RECEIPT && selectedOrder != null) View.VISIBLE else View.GONE

        if (resolvedMode == PosMode.RECEIPT) {
            selectedOrder = null
            receiptAdapter.selectedOrderId = null
            binding.panelTitle.text = getString(R.string.collect_payment)
            binding.checkoutButton.text = getString(R.string.collect_payment)
            binding.cancelOrderButton.visibility = View.GONE
            loadOpenOrders()
            startReceiptRefresh()
        } else {
            refreshJob?.cancel()
            selectedOrder = null
            binding.panelTitle.text = getString(R.string.current_order)
            binding.checkoutButton.text = getString(R.string.place_order)
            binding.cancelOrderButton.visibility = View.GONE
            syncOrderTypeUi(if (binding.orderTypeSpinner.selectedItemPosition == 1) "dine_in" else "takeaway")
            renderCart()
        }
    }

    private fun startReceiptRefresh() {
        refreshJob?.cancel()
        refreshJob = lifecycleScope.launch {
            while (isActive) {
                delay(RECEIPT_REFRESH_MS)
                if (posMode == PosMode.RECEIPT) {
                    loadOpenOrders(silent = true)
                }
            }
        }
    }

    private fun loadCatalog() {
        lifecycleScope.launch {
            binding.refreshProgress.visibility = View.VISIBLE
            try {
                val catalog = withContext(Dispatchers.IO) {
                    PosCatalog(
                        products = api.fetchProducts(),
                        categories = api.fetchCategories(),
                        currencies = api.fetchCurrencies(),
                        customers = api.fetchCustomers(),
                    )
                }
                products = catalog.products
                allCurrencies = catalog.currencies
                currencies = catalog.currencies.filter {
                    it.is_active && (it.is_base || !it.current_rate.isNullOrBlank())
                }
                customers = catalog.customers
                val visibleCategories = catalog.categories.filter { category ->
                    products.any { it.category == category.id }
                }
                val chips = listOf(CategoryChipAdapter.Chip(null, getString(R.string.category_all))) +
                    visibleCategories.map { CategoryChipAdapter.Chip(it.id, it.name) }
                categoryAdapter.submit(chips)
                if (activeCategoryId != null && visibleCategories.none { it.id == activeCategoryId }) {
                    activeCategoryId = null
                }
                categoryAdapter.select(activeCategoryId)
                setupCurrencyButtons()
                renderProducts()
            } catch (err: ApiException) {
                handleApiError(err)
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message ?: ""))
            } finally {
                binding.refreshProgress.visibility = View.GONE
            }
        }
    }

    private fun usableCurrencies(): List<Currency> {
        return currencies.filter { it.is_base || !it.current_rate.isNullOrBlank() }
    }

    private fun setupCurrencyButtons() {
        renderCurrencyButtons()
    }

    private fun renderCurrencyButtons() {
        binding.currencyButtonGrid.removeAllViews()
        val usable = usableCurrencies()
        val hasCurrencies = usable.isNotEmpty()
        binding.currencyButtonGrid.visibility = if (hasCurrencies) View.VISIBLE else View.GONE
        binding.currencyEmptyLabel.visibility = if (hasCurrencies) View.GONE else View.VISIBLE
        if (!hasCurrencies) {
            selectedCurrencyId = null
            return
        }
        if (selectedCurrencyId == null || usable.none { it.id == selectedCurrencyId }) {
            selectedCurrencyId = usable.firstOrNull { it.is_base }?.id ?: usable.first().id
        }
        for (currency in usable) {
            val button = LayoutInflater.from(this)
                .inflate(R.layout.item_category_chip, binding.currencyButtonGrid, false) as MaterialButton
            button.apply {
                text = currencyButtonLabel(currency)
                isCheckable = true
                isChecked = currency.id == selectedCurrencyId
                isAllCaps = false
                tag = currency.id
                layoutParams = GridLayout.LayoutParams().apply {
                    width = 0
                    height = GridLayout.LayoutParams.WRAP_CONTENT
                    columnSpec = GridLayout.spec(GridLayout.UNDEFINED, 1f)
                    setMargins(6, 6, 6, 6)
                }
                setOnClickListener { onCurrencySelected(currency.id) }
            }
            binding.currencyButtonGrid.addView(button)
        }
    }

    private fun onCurrencySelected(currencyId: Int) {
        selectedCurrencyId = currencyId
        for (index in 0 until binding.currencyButtonGrid.childCount) {
            val button = binding.currencyButtonGrid.getChildAt(index) as MaterialButton
            button.isChecked = button.tag == currencyId
        }
        updateReceiptCheckoutState()
    }

    private fun currencyButtonLabel(currency: Currency): String {
        return if (currency.is_base) {
            currency.name
        } else {
            val rate = currency.current_rate?.takeIf { it.isNotBlank() }
            if (rate != null) "${currency.name} · $rate" else currency.name
        }
    }

    private fun loadOpenOrders(silent: Boolean = false) {
        lifecycleScope.launch {
            if (!silent) binding.refreshProgress.visibility = View.VISIBLE
            try {
                val orders = withContext(Dispatchers.IO) { api.fetchOpenOrders() }
                    .sortedByDescending { it.created_at }
                openOrders = orders
                receiptAdapter.openOrders = orders
                receiptAdapter.submitList(orders)
                selectedOrder = selectedOrder?.let { current ->
                    orders.find { it.id == current.id }
                }
                if (selectedOrder == null) {
                    binding.paymentSection.visibility = View.GONE
                }
                if (posMode == PosMode.RECEIPT) {
                    renderReceiptPanel()
                }
            } catch (err: ApiException) {
                if (!silent) handleApiError(err)
            } catch (err: Exception) {
                if (!silent) showError(getString(R.string.connection_failed, err.message ?: ""))
            } finally {
                if (!silent) binding.refreshProgress.visibility = View.GONE
            }
        }
    }

    private fun handleProductTap(product: Product) {
        if (product.hasActiveAddons()) {
            AddonPickerDialog.show(this, product) { addons, notes ->
                addToCart(product, addons, notes)
            }
            return
        }
        addToCart(product)
    }

    private fun addToCart(
        product: Product,
        addons: List<com.cafedeparis.kitchen.data.CartAddon> = emptyList(),
        notes: String = "",
    ) {
        val basePrice = product.selling_price.toDoubleOrNull() ?: 0.0
        val addonPrice = addons.sumOf { it.price }
        val unitPrice = basePrice + addonPrice
        val lineKey = cartLineKey(product.id, addons.map { it.id }, notes)
        val existing = cart[lineKey]
        if (existing != null) {
            existing.quantity += 1.0
        } else {
            cart[lineKey] = CartLine(
                lineKey = lineKey,
                productId = product.id,
                name = product.name,
                price = unitPrice,
                quantity = 1.0,
                addons = addons,
                notes = notes,
            )
        }
        renderCart()
    }

    private fun updateCartQuantity(lineKey: String, quantity: Double) {
        if (quantity <= 0.0) {
            cart.remove(lineKey)
        } else {
            cart[lineKey]?.quantity = quantity
        }
        renderCart()
    }

    private fun renderCart() {
        binding.cartList.adapter = cartAdapter
        val lines = cart.values.toList()
        cartAdapter.submitList(lines)
        val hasLines = lines.isNotEmpty()
        binding.emptyCartLabel.visibility = if (hasLines) View.GONE else View.VISIBLE
        binding.cartList.visibility = if (hasLines) View.VISIBLE else View.GONE
        binding.clearButton.isEnabled = hasLines
        binding.checkoutButton.isEnabled = hasLines
        binding.cancelOrderButton.visibility = View.GONE
        val total = lines.sumOf { it.price * it.quantity }
        binding.totalCaption.setText(R.string.total)
        binding.totalLabel.text = ProductAdapter.formatMoney(total, baseCurrencySymbol())
        binding.exchangeRateLabel.visibility = View.GONE
    }

    private fun renderProducts() {
        var filtered = if (activeCategoryId == null) {
            products
        } else {
            products.filter { it.category == activeCategoryId }
        }
        if (searchQuery.isNotBlank()) {
            filtered = filtered.filter { product ->
                product.name.lowercase().contains(searchQuery) ||
                    product.category_name?.lowercase()?.contains(searchQuery) == true
            }
        }
        productAdapter.submitList(filtered)
    }

    private fun renderReceiptPanel() {
        val order = selectedOrder
        if (order == null) {
            receiptPaymentOrderId = null
            binding.cartList.adapter = cartAdapter
            cartAdapter.submitList(emptyList())
            binding.emptyCartLabel.visibility = View.VISIBLE
            binding.cartList.visibility = View.GONE
            binding.paymentSection.visibility = View.GONE
            binding.clearButton.isEnabled = false
            binding.checkoutButton.isEnabled = false
            binding.cancelOrderButton.visibility = View.GONE
            binding.totalCaption.setText(R.string.total)
            binding.totalLabel.text = ProductAdapter.formatMoney(0.0, baseCurrencySymbol())
            binding.exchangeRateLabel.visibility = View.GONE
            return
        }

        val orderChanged = receiptPaymentOrderId != order.id
        receiptPaymentOrderId = order.id

        val lines = receiptOrders().flatMap { tableOrder ->
            tableOrder.items.map { item ->
                val qty = item.quantity.toDoubleOrNull() ?: 1.0
                val price = item.price.toDoubleOrNull() ?: 0.0
                val addonPrice = item.addons.sumOf { it.price.toDoubleOrNull() ?: 0.0 }
                CartLine(
                    lineKey = "order-${tableOrder.id}-${item.id}",
                    productId = item.id,
                    name = if (receiptOrders().size > 1) {
                        "#${tableOrder.id} · ${item.product_name}"
                    } else {
                        item.product_name
                    },
                    price = price + addonPrice,
                    quantity = qty,
                    addons = item.addons.map { addon ->
                        com.cafedeparis.kitchen.data.CartAddon(
                            id = 0,
                            name = addon.name,
                            price = addon.price.toDoubleOrNull() ?: 0.0,
                        )
                    },
                    notes = item.notes,
                )
            }
        }
        binding.cartList.adapter = receiptCartAdapter
        receiptCartAdapter.submitList(lines)
        binding.emptyCartLabel.visibility = View.GONE
        binding.cartList.visibility = View.VISIBLE
        binding.paymentSection.visibility = View.VISIBLE
        binding.clearButton.isEnabled = false
        binding.cancelOrderButton.visibility = View.VISIBLE
        binding.cancelOrderButton.isEnabled = true
        if (orderChanged) {
            paymentMethod = PaymentMethod.CASH
            binding.paymentMethodToggle.check(binding.cashPaymentButton.id)
            setupCustomerSpinner(order.customer)
            binding.splitPaymentEnabled.isChecked = false
            clearSplitPaymentInputs()
        }
        syncPaymentMethodUi()
        renderCurrencyButtons()
        updateReceiptCheckoutState()
    }

    private fun selectedCurrency(): Currency? {
        val currencyId = selectedCurrencyId ?: return null
        return usableCurrencies().firstOrNull { it.id == currencyId }
    }

    private fun currentOrderType(): String {
        return if (binding.orderTypeSpinner.selectedItemPosition == 1) "dine_in" else "takeaway"
    }

    private fun placeOrder() {
        if (cart.isEmpty()) return
        binding.checkoutButton.isEnabled = false
        lifecycleScope.launch {
            try {
                val tableNumber = if (currentOrderType() == "dine_in") selectedTableName else null
                val existingTableOrderId = tableNumber?.trim()?.takeIf { it.isNotEmpty() }?.let { table ->
                    openOrdersForTable(table).firstOrNull()?.id
                }
                val order = withContext(Dispatchers.IO) {
                    api.createOrder(currentOrderType(), tableNumber, cart.values.toList())
                }
                cart.clear()
                renderCart()
                loadOpenOrders(silent = true)
                printOrderTicket(order)
                val addedToExisting = existingTableOrderId != null && order.id == existingTableOrderId
                Toast.makeText(
                    this@PosActivity,
                    if (addedToExisting) {
                        getString(
                            R.string.items_added_to_order,
                            order.id,
                            ProductAdapter.formatMoney(order.total_amount, baseCurrencySymbol()),
                        )
                    } else {
                        getString(
                            R.string.order_placed,
                            order.id,
                            ProductAdapter.formatMoney(order.total_amount, baseCurrencySymbol()),
                        )
                    },
                    Toast.LENGTH_LONG,
                ).show()
            } catch (err: ApiException) {
                handleApiError(err)
                renderCart()
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message ?: ""))
                renderCart()
            }
        }
    }

    private fun cancelSelectedOrder() {
        val order = selectedOrder ?: return
        MaterialAlertDialogBuilder(this)
            .setMessage(getString(R.string.cancel_order_confirm, order.id))
            .setPositiveButton(R.string.cancel_order) { _, _ ->
                performCancelOrder(order)
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun performCancelOrder(order: KitchenOrder) {
        binding.cancelOrderButton.isEnabled = false
        lifecycleScope.launch {
            try {
                withContext(Dispatchers.IO) {
                    api.cancelOrder(order.id)
                }
                Toast.makeText(
                    this@PosActivity,
                    getString(R.string.order_cancelled, order.id),
                    Toast.LENGTH_SHORT,
                ).show()
                selectedOrder = null
                receiptAdapter.selectedOrderId = null
                loadOpenOrders(silent = true)
                renderReceiptPanel()
            } catch (err: ApiException) {
                handleApiError(err)
                binding.cancelOrderButton.isEnabled = selectedOrder != null
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message ?: ""))
                binding.cancelOrderButton.isEnabled = selectedOrder != null
            }
        }
    }

    private fun paySelectedOrder() {
        val order = selectedOrder ?: return
        val total = receiptInclusiveTotal()
        val combined = receiptOrders().size > 1

        if (paymentMethod == PaymentMethod.ACCOUNT) {
            val customer = selectedCustomer()
            if (customer == null) {
                Toast.makeText(this, R.string.select_customer_account, Toast.LENGTH_SHORT).show()
                return
            }
            val available = customer.availableCredit()
            if (available < total) {
                Toast.makeText(
                    this,
                    getString(
                        R.string.insufficient_account_balance,
                        ProductAdapter.formatMoney(available, baseCurrencySymbol()),
                    ),
                    Toast.LENGTH_LONG,
                ).show()
                return
            }
        } else {
            if (isSplitPaymentActive()) {
                val lines = splitPaymentLines()
                val allocated = lines.sumOf { it.third }
                if (lines.isEmpty() || allocated + 0.005 < total) {
                    Toast.makeText(
                        this,
                        getString(
                            R.string.split_must_cover,
                            ProductAdapter.formatMoney(total, baseCurrencySymbol()),
                            ProductAdapter.formatMoney(allocated, baseCurrencySymbol()),
                        ),
                        Toast.LENGTH_LONG,
                    ).show()
                    return
                }
            } else if (selectedCurrency() == null) {
                Toast.makeText(this, R.string.select_currency, Toast.LENGTH_SHORT).show()
                return
            }
        }

        binding.checkoutButton.isEnabled = false
        lifecycleScope.launch {
            try {
                val paid = withContext(Dispatchers.IO) {
                    if (paymentMethod == PaymentMethod.ACCOUNT) {
                        val customerId = selectedCustomer()?.id
                        if (order.customer != customerId) {
                            api.updateOrderCustomer(order.id, customerId)
                        }
                        api.payOrderFromAccount(order.id)
                    } else {
                        val lines = if (isSplitPaymentActive()) splitPaymentLines() else emptyList()
                        if (lines.isNotEmpty()) {
                            api.payOrderWithTenders(
                                order.id,
                                lines.map { it.first to String.format("%.2f", it.second) },
                            )
                        } else {
                            api.payOrderCash(order.id, selectedCurrency()!!.id)
                        }
                    }
                }
                binding.splitPaymentEnabled.isChecked = false
                clearSplitPaymentInputs()
                printReceipt(paid)
                if (paymentMethod == PaymentMethod.ACCOUNT && paid.customer != null) {
                    val updatedBalance = paid.customer_account_balance
                    if (!updatedBalance.isNullOrBlank()) {
                        customers = customers.map { customer ->
                            if (customer.id == paid.customer) {
                                customer.copy(account_balance = updatedBalance)
                            } else {
                                customer
                            }
                        }
                    }
                }
                val message = if (paymentMethod == PaymentMethod.ACCOUNT) {
                    getString(
                        R.string.order_paid_account,
                        paid.id,
                        ProductAdapter.formatMoney(paid.total_amount, baseCurrencySymbol()),
                    )
                } else {
                    val paidSymbol = paid.payment_currency_symbol
                        ?.takeIf { it.isNotBlank() }
                        ?: selectedCurrency()?.symbol?.takeIf { it.isNotBlank() }
                        ?: baseCurrencySymbol()
                    val paidAmount = ProductAdapter.formatMoney(
                        paid.amount_paid ?: paid.total_amount,
                        paidSymbol,
                    )
                    if (combined && !order.table_number.isNullOrBlank()) {
                        getString(R.string.table_paid, order.table_number, paidAmount)
                    } else {
                        getString(
                            R.string.order_paid,
                            paid.id,
                            paid.payment_currency_name ?: selectedCurrency()?.name.orEmpty(),
                            paidAmount,
                        )
                    }
                }
                Toast.makeText(this@PosActivity, message, Toast.LENGTH_LONG).show()
                selectedOrder = null
                receiptPaymentOrderId = null
                receiptAdapter.selectedOrderId = null
                loadOpenOrders()
            } catch (err: ApiException) {
                handleApiError(err)
                renderReceiptPanel()
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message ?: ""))
                renderReceiptPanel()
            }
        }
    }

    private fun handleApiError(err: ApiException) {
        if (err.statusCode == 401) {
            Toast.makeText(this, R.string.session_expired, Toast.LENGTH_LONG).show()
            session.clearLogin()
            startActivity(Intent(this, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            })
            finish()
        } else {
            showError(err.message ?: getString(R.string.load_failed))
        }
    }

    private fun showError(message: String) {
        binding.errorBanner.text = message
        binding.errorBanner.visibility = View.VISIBLE
    }

    private fun paymentOptionsForAmount(baseAmount: Double): List<PaymentOptionLine> {
        return usableCurrencies().mapNotNull { currency ->
            val rate = paymentRate(currency) ?: return@mapNotNull null
            PaymentOptionLine(
                name = currency.name.ifBlank { currency.code },
                symbol = currency.symbol,
                amount = roundMoney(baseAmount * rate),
            )
        }
    }

    private suspend fun printOrderTicket(order: KitchenOrder) {
        val printerAddress = session.printerAddress
        if (printerAddress.isNullOrBlank()) {
            withContext(Dispatchers.Main) {
                Toast.makeText(this@PosActivity, R.string.printer_not_configured, Toast.LENGTH_SHORT).show()
            }
            return
        }

        val baseCurrency = currencies.firstOrNull { it.is_base }
        val total = order.total_amount.toDoubleOrNull() ?: 0.0
        val options = OrderSlipPrintOptions(
            baseCurrencyCode = baseCurrency?.code?.takeIf { it.isNotBlank() }
                ?: baseCurrency?.name,
            paymentOptions = paymentOptionsForAmount(total),
        )

        try {
            withContext(Dispatchers.IO) {
                printer.printOrderSlip(printerAddress, order, options)
            }
        } catch (err: PrinterException) {
            withContext(Dispatchers.Main) {
                showError(getString(R.string.print_failed, err.message ?: ""))
            }
        } catch (err: SecurityException) {
            withContext(Dispatchers.Main) {
                requestBluetoothIfNeeded()
                showError(getString(R.string.bluetooth_permission_required))
            }
        } catch (err: Exception) {
            withContext(Dispatchers.Main) {
                showError(getString(R.string.print_failed, err.message ?: ""))
            }
        }
    }

    private suspend fun printReceipt(order: KitchenOrder) {
        val printerAddress = session.printerAddress
        if (printerAddress.isNullOrBlank()) {
            withContext(Dispatchers.Main) {
                Toast.makeText(this@PosActivity, R.string.printer_not_configured, Toast.LENGTH_SHORT).show()
            }
            return
        }

        val total = order.total_amount.toDoubleOrNull() ?: 0.0
        val paymentOptions = paymentOptionsForAmount(total)

        try {
            withContext(Dispatchers.IO) {
                printer.printReceipt(printerAddress, order, paymentOptions)
            }
        } catch (err: PrinterException) {
            withContext(Dispatchers.Main) {
                showError(getString(R.string.print_failed, err.message ?: ""))
            }
        } catch (err: SecurityException) {
            withContext(Dispatchers.Main) {
                requestBluetoothIfNeeded()
                showError(getString(R.string.bluetooth_permission_required))
            }
        } catch (err: Exception) {
            withContext(Dispatchers.Main) {
                showError(getString(R.string.print_failed, err.message ?: ""))
            }
        }
    }

    private fun requestBluetoothIfNeeded() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_CONNECT)
            == PackageManager.PERMISSION_GRANTED
        ) {
            return
        }
        bluetoothPermissionLauncher.launch(Manifest.permission.BLUETOOTH_CONNECT)
    }

    private enum class PosMode {
        ORDER,
        RECEIPT,
    }

    private enum class PaymentMethod {
        CASH,
        ACCOUNT,
    }

    private data class PosCatalog(
        val products: List<Product>,
        val categories: List<com.cafedeparis.kitchen.data.ProductCategory>,
        val currencies: List<Currency>,
        val customers: List<Customer>,
    )

    companion object {
        private const val RECEIPT_REFRESH_MS = 10_000L
    }
}
