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
import android.view.MenuItem
import android.widget.PopupMenu
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.core.widget.doAfterTextChanged
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
import com.cafedeparis.kitchen.data.ExpenseReport
import com.cafedeparis.kitchen.data.KitchenOrder
import com.cafedeparis.kitchen.data.OrderSlipPrintOptions
import com.cafedeparis.kitchen.data.PaymentOptionLine
import com.cafedeparis.kitchen.data.Product
import com.cafedeparis.kitchen.data.SessionManager
import com.cafedeparis.kitchen.data.Supplier
import com.cafedeparis.kitchen.databinding.ActivityPosBinding
import com.cafedeparis.kitchen.databinding.DialogCustomerPaymentBinding
import com.cafedeparis.kitchen.databinding.DialogCustomerPickerBinding
import com.cafedeparis.kitchen.databinding.DialogDayEndBinding
import com.cafedeparis.kitchen.databinding.DialogFiscalDayBinding
import com.cafedeparis.kitchen.databinding.DialogFiscalInvoicesBinding
import java.util.Locale
import com.cafedeparis.kitchen.databinding.DialogExpenseBinding
import com.cafedeparis.kitchen.databinding.DialogOrderPickerBinding
import com.cafedeparis.kitchen.databinding.DialogTablePickerBinding
import com.cafedeparis.kitchen.print.EscPosPrinter
import com.cafedeparis.kitchen.print.PrinterException
import com.cafedeparis.kitchen.data.FiscalDayStatus
import com.cafedeparis.kitchen.data.cartLineKey
import com.cafedeparis.kitchen.data.receiptHeaderLabel
import com.cafedeparis.kitchen.ui.AddonPickerDialog
import com.cafedeparis.kitchen.ui.CartLineAdapter
import com.cafedeparis.kitchen.ui.CategoryChipAdapter
import com.cafedeparis.kitchen.ui.DiningTableAdapter
import com.cafedeparis.kitchen.ui.FiscalInvoiceAdapter
import com.cafedeparis.kitchen.ui.ProductAdapter
import com.cafedeparis.kitchen.ui.ReceiptOrderAdapter
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.textfield.TextInputEditText
import com.google.android.material.textfield.TextInputLayout
import java.text.SimpleDateFormat
import java.util.Date
import java.util.TimeZone
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlin.coroutines.resume

class PosActivity : KeepScreenOnActivity() {

    private data class CustomerPaymentChoice<T>(
        val label: String,
        val value: T,
    ) {
        override fun toString(): String = label
    }

    private sealed class TakeawayPick {
        data object Cancelled : TakeawayPick()
        data object NewOrder : TakeawayPick()
        data class Existing(val orderId: Int) : TakeawayPick()
    }

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
    private var selectedAccountCustomer: Customer? = null
    private var diningTables: List<DiningTable> = emptyList()
    private var openOrders: List<KitchenOrder> = emptyList()
    private var selectedOrder: KitchenOrder? = null
    private var receiptPaymentOrderId: Int? = null
    private var selectedTableName: String? = null
    private val selectedTransferKeys = linkedSetOf<String>()
    private var tablePickerPurpose: TablePickerPurpose = TablePickerPurpose.SELECT
    private var activeCategoryId: Int? = null
    private var searchQuery: String = ""
    private var posMode: PosMode = PosMode.ORDER
    private var paymentMethod: PaymentMethod = PaymentMethod.CASH
    private var selectedCurrencyId: Int? = null
    private var tablePickerDialog: androidx.appcompat.app.AlertDialog? = null
    private var orderPickerDialog: androidx.appcompat.app.AlertDialog? = null
    private var dayEndDialog: androidx.appcompat.app.AlertDialog? = null
    private var fiscalDayDialog: androidx.appcompat.app.AlertDialog? = null
    private var fiscalDayDialogBinding: DialogFiscalDayBinding? = null
    private var fiscalDayStatus: FiscalDayStatus? = null
    private var fiscalInvoicesDialog: androidx.appcompat.app.AlertDialog? = null
    private var fiscalInvoicesDialogBinding: DialogFiscalInvoicesBinding? = null
    private var fiscalInvoiceAdapter: FiscalInvoiceAdapter? = null
    private var expenseDialog: androidx.appcompat.app.AlertDialog? = null
    private var customerPaymentDialog: androidx.appcompat.app.AlertDialog? = null
    private var customerPickerDialog: androidx.appcompat.app.AlertDialog? = null
    private var refreshJob: Job? = null
    private var errorHideJob: Job? = null
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
    private val receiptCartAdapter = CartLineAdapter(
        editable = false,
        transferable = true,
        onTransferToggle = { line, selected ->
            if (selected) selectedTransferKeys.add(line.lineKey)
            else selectedTransferKeys.remove(line.lineKey)
            updateTransferButtonState()
        },
    ) { _, _ -> }
    private val receiptAdapter = ReceiptOrderAdapter(
        onOrderClick = ::onReceiptOrderSelected,
        onOrderLongClick = ::onReceiptOrderLongPress,
    )
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

    private fun onReceiptOrderLongPress(order: KitchenOrder) {
        onReceiptOrderSelected(order)
        lifecycleScope.launch {
            try {
                withContext(Dispatchers.IO) {
                    api.authorizeBillPrint(order.id)
                }
                Toast.makeText(this@PosActivity, R.string.printing_bill, Toast.LENGTH_SHORT).show()
                printOrderTicket(order, documentTitle = getString(R.string.bill_document_title))
            } catch (err: ApiException) {
                if (err.statusCode == 403) {
                    promptBillReprintAccessCode(order)
                } else {
                    handleApiError(err)
                }
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message ?: ""))
            }
        }
    }

    private fun promptBillReprintAccessCode(order: KitchenOrder) {
        val input = TextInputEditText(this).apply {
            inputType = android.text.InputType.TYPE_CLASS_NUMBER
            hint = getString(R.string.access_code_hint)
            filters = arrayOf(android.text.InputFilter.LengthFilter(4))
        }
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val pad = (16 * resources.displayMetrics.density).toInt()
            setPadding(pad, pad / 2, pad, 0)
            addView(input)
        }
        fun submitCode(code: String) {
            if (!code.matches(Regex("^\\d{4}$"))) {
                Toast.makeText(this, R.string.access_code_invalid, Toast.LENGTH_SHORT).show()
                return
            }
            lifecycleScope.launch {
                try {
                    withContext(Dispatchers.IO) {
                        api.authorizeBillPrint(order.id, code)
                    }
                    Toast.makeText(this@PosActivity, R.string.printing_bill, Toast.LENGTH_SHORT).show()
                    printOrderTicket(
                        order,
                        documentTitle = getString(R.string.bill_document_title),
                    )
                } catch (err: ApiException) {
                    handleApiError(err)
                } catch (err: Exception) {
                    showError(getString(R.string.connection_failed, err.message ?: ""))
                }
            }
        }
        val dialog = MaterialAlertDialogBuilder(this)
            .setTitle(R.string.bill_reprint_title)
            .setMessage(R.string.bill_reprint_message)
            .setView(container)
            .setNegativeButton(android.R.string.cancel, null)
            .setPositiveButton(android.R.string.ok) { _, _ ->
                submitCode(input.text?.toString()?.trim().orEmpty())
            }
            .create()
        input.doAfterTextChanged { editable ->
            val code = editable?.toString()?.trim().orEmpty()
            if (code.matches(Regex("^\\d{4}$")) && dialog.isShowing) {
                dialog.dismiss()
                submitCode(code)
            }
        }
        dialog.show()
        input.requestFocus()
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

        binding.productList.layoutManager = GridLayoutManager(this, 2)
        binding.productList.adapter = productAdapter
        binding.categoryList.layoutManager = GridLayoutManager(this, 2)
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
        errorHideJob?.cancel()
        tablePickerDialog?.dismiss()
        orderPickerDialog?.dismiss()
        dayEndDialog?.dismiss()
        expenseDialog?.dismiss()
        customerPaymentDialog?.dismiss()
        customerPickerDialog?.dismiss()
        super.onDestroy()
    }

    private fun todayIso(): String {
        return SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date())
    }

    private fun nowIso(): String {
        return SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US).apply {
            timeZone = TimeZone.getDefault()
        }.format(Date())
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
            .setNeutralButton(R.string.print_expenses, null)
            .setPositiveButton(R.string.save, null)
            .create()

        expenseDialog?.setOnShowListener {
            expenseDialog?.getButton(androidx.appcompat.app.AlertDialog.BUTTON_POSITIVE)
                ?.setOnClickListener {
                    saveExpense(
                        dialogBinding = dialogBinding,
                        expenseCurrencies = expenseCurrencies,
                        activeSuppliers = activeSuppliers,
                    )
                }
            expenseDialog?.getButton(androidx.appcompat.app.AlertDialog.BUTTON_NEUTRAL)
                ?.setOnClickListener {
                    printExpensesForDate(dialogBinding)
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

    private fun printExpensesForDate(dialogBinding: DialogExpenseBinding) {
        val expenseDate = dialogBinding.expenseDateInput.text?.toString()?.trim().orEmpty()
            .ifBlank { todayIso() }
        if (expenseDate.isBlank()) {
            dialogBinding.expenseDateInput.error = getString(R.string.print_expenses_date_required)
            dialogBinding.expenseDateInput.requestFocus()
            return
        }

        val printerAddress = session.printerAddress
        if (printerAddress.isNullOrBlank()) {
            Toast.makeText(this, R.string.printer_not_configured, Toast.LENGTH_LONG).show()
            return
        }

        val printButton = expenseDialog
            ?.getButton(androidx.appcompat.app.AlertDialog.BUTTON_NEUTRAL)
        printButton?.isEnabled = false

        lifecycleScope.launch {
            binding.refreshProgress.visibility = View.VISIBLE
            Toast.makeText(this@PosActivity, R.string.print_expenses_printing, Toast.LENGTH_SHORT).show()
            try {
                val expenses = withContext(Dispatchers.IO) { api.fetchExpenses(expenseDate) }
                val report = ExpenseReport(
                    expenseDate = expenseDate,
                    printedAt = nowIso(),
                    branchName = session.branchName.orEmpty(),
                    expenses = expenses,
                )
                withContext(Dispatchers.IO) {
                    printer.printExpenses(printerAddress, report)
                }
                Toast.makeText(this@PosActivity, R.string.print_expenses_printed, Toast.LENGTH_SHORT).show()
            } catch (err: ApiException) {
                handleApiError(err)
            } catch (err: PrinterException) {
                showError(getString(R.string.print_failed, err.message ?: ""))
            } catch (err: SecurityException) {
                requestBluetoothIfNeeded()
                showError(getString(R.string.bluetooth_permission_required))
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message ?: ""))
            } finally {
                binding.refreshProgress.visibility = View.GONE
                printButton?.isEnabled = true
            }
        }
    }

    private fun openStockTake() {
        startActivity(Intent(this, StockTakeActivity::class.java))
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
        var selectedCustomer: Customer? = null
        dialogBinding.customerPaymentCustomerInput.setText(
            getString(R.string.customer_payment_select_hint),
        )

        val paymentCurrencies = allCurrencies.filter { it.is_active }.ifEmpty { allCurrencies }
        if (paymentCurrencies.isEmpty()) {
            Toast.makeText(this, R.string.customer_payment_currency_required, Toast.LENGTH_LONG).show()
            return
        }
        val currencyChoices = paymentCurrencies.map { currency ->
            val symbol = currency.symbol.takeIf { it.isNotBlank() }?.let { " ($it)" }.orEmpty()
            CustomerPaymentChoice(
                "${currency.name.ifBlank { currency.code }}$symbol",
                currency,
            )
        }
        dialogBinding.customerPaymentCurrencyInput.setAdapter(ArrayAdapter(
            this,
            android.R.layout.simple_spinner_dropdown_item,
            currencyChoices,
        ))
        val baseIndex = paymentCurrencies.indexOfFirst { it.is_base }.takeIf { it >= 0 } ?: 0
        var selectedCurrencyChoice: CustomerPaymentChoice<Currency>? = currencyChoices[baseIndex]
        dialogBinding.customerPaymentCurrencyInput.setText(
            selectedCurrencyChoice?.label,
            false,
        )

        fun updateBalance() {
            val customer = selectedCustomer
            dialogBinding.customerPaymentBalanceLabel.text = if (customer == null) {
                getString(R.string.customer_payment_select_hint)
            } else {
                getString(
                    R.string.customer_payment_balance,
                    ProductAdapter.formatMoney(customer.account_balance),
                )
            }
        }

        dialogBinding.customerPaymentCustomerInput.setOnClickListener {
            openCustomerPickerDialog(
                includeWalkIn = false,
                onSelected = { customer ->
                    selectedCustomer = customer
                    dialogBinding.customerPaymentCustomerInput.setText(
                        customer?.full_name
                            ?: getString(R.string.customer_payment_select_hint),
                    )
                    updateBalance()
                },
            )
        }
        dialogBinding.customerPaymentCustomerLayout.setEndIconOnClickListener {
            dialogBinding.customerPaymentCustomerInput.performClick()
        }
        dialogBinding.customerPaymentCurrencyInput.setOnItemClickListener {
                parent, _, position, _ ->
            @Suppress("UNCHECKED_CAST")
            selectedCurrencyChoice =
                parent.getItemAtPosition(position) as CustomerPaymentChoice<Currency>
        }
        updateBalance()

        customerPaymentDialog = MaterialAlertDialogBuilder(this)
            .setTitle(R.string.customer_payment_title)
            .setView(dialogBinding.root)
            .setNegativeButton(android.R.string.cancel, null)
            .setNeutralButton(R.string.customer_statement_print, null)
            .setPositiveButton(R.string.customer_payment_record, null)
            .create()

        customerPaymentDialog?.setOnShowListener {
            customerPaymentDialog?.getButton(androidx.appcompat.app.AlertDialog.BUTTON_POSITIVE)
                ?.setOnClickListener {
                    saveCustomerPayment(
                        dialogBinding,
                        selectedCustomer,
                        selectedCurrencyChoice?.value,
                    )
                }
            customerPaymentDialog?.getButton(androidx.appcompat.app.AlertDialog.BUTTON_NEUTRAL)
                ?.setOnClickListener {
                    printCustomerAccountStatement(selectedCustomer)
                }
        }
        customerPaymentDialog?.show()
    }

    private fun printCustomerAccountStatement(customer: Customer?) {
        if (customer == null) {
            Toast.makeText(this, R.string.customer_payment_customer_required, Toast.LENGTH_SHORT).show()
            return
        }
        val printerAddress = session.printerAddress
        if (printerAddress.isNullOrBlank()) {
            Toast.makeText(this, R.string.printer_not_configured, Toast.LENGTH_LONG).show()
            return
        }

        val printButton = customerPaymentDialog
            ?.getButton(androidx.appcompat.app.AlertDialog.BUTTON_NEUTRAL)
        printButton?.isEnabled = false

        lifecycleScope.launch {
            binding.refreshProgress.visibility = View.VISIBLE
            Toast.makeText(this@PosActivity, R.string.customer_statement_printing, Toast.LENGTH_SHORT).show()
            try {
                val statement = withContext(Dispatchers.IO) {
                    api.fetchCustomerStatement(customer.id, allTime = true)
                }
                val baseCurrency = allCurrencies.firstOrNull { it.is_base }
                    ?: currencies.firstOrNull { it.is_base }
                withContext(Dispatchers.IO) {
                    printer.printCustomerStatement(
                        deviceAddress = printerAddress,
                        customer = customer.copy(account_balance = statement.currentBalance),
                        statement = statement,
                        branchName = session.branchName,
                        baseCurrencyCode = baseCurrency?.code?.takeIf { it.isNotBlank() }
                            ?: baseCurrency?.name,
                    )
                }
                Toast.makeText(
                    this@PosActivity,
                    R.string.customer_statement_printed,
                    Toast.LENGTH_SHORT,
                ).show()
            } catch (err: ApiException) {
                handleApiError(err)
                Toast.makeText(this@PosActivity, err.message, Toast.LENGTH_LONG).show()
            } catch (err: PrinterException) {
                showError(getString(R.string.print_failed, err.message ?: ""))
            } catch (err: SecurityException) {
                requestBluetoothIfNeeded()
                showError(getString(R.string.bluetooth_permission_required))
            } catch (err: Exception) {
                val message = getString(R.string.connection_failed, err.message ?: "")
                showError(message)
                Toast.makeText(this@PosActivity, message, Toast.LENGTH_LONG).show()
            } finally {
                binding.refreshProgress.visibility = View.GONE
                printButton?.isEnabled = true
            }
        }
    }

    private fun parseDepositAmount(raw: String): Double? {
        val normalized = raw.trim().replace(',', '.')
        return normalized.toDoubleOrNull()
    }

    private fun saveCustomerPayment(
        dialogBinding: DialogCustomerPaymentBinding,
        customer: Customer?,
        currency: Currency?,
    ) {
        val amountRaw = dialogBinding.customerPaymentAmountInput.text?.toString()?.trim().orEmpty()
        val notes = dialogBinding.customerPaymentNotesInput.text?.toString()?.trim().orEmpty()

        if (customer == null) {
            Toast.makeText(this, R.string.customer_payment_customer_required, Toast.LENGTH_SHORT).show()
            return
        }
        val amount = parseDepositAmount(amountRaw)
        if (amount == null || amount == 0.0 || (amount < 0.0 && !session.isSuperuser)) {
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
                setupCustomerSearch(customer.id)
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
                            openStockTake()
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

    private fun openFiscalDayDialog() {
        if (!session.fiscalizationEnabled) {
            Toast.makeText(this, R.string.fiscal_day_not_configured, Toast.LENGTH_LONG).show()
            return
        }
        val dialogBinding = DialogFiscalDayBinding.inflate(layoutInflater)
        fiscalDayDialogBinding = dialogBinding
        renderFiscalDayDialog(fiscalDayStatus)

        dialogBinding.fiscalDayRefreshButton.setOnClickListener { refreshFiscalDayStatus() }
        dialogBinding.fiscalDayOpenButton.setOnClickListener { runFiscalDayAction(open = true) }
        dialogBinding.fiscalDayCloseDayButton.setOnClickListener { runFiscalDayAction(open = false) }

        fiscalDayDialog = MaterialAlertDialogBuilder(this)
            .setTitle(R.string.fiscal_day_title)
            .setView(dialogBinding.root)
            .setNegativeButton(android.R.string.cancel, null)
            .create()
        fiscalDayDialog?.setOnDismissListener {
            fiscalDayDialog = null
            fiscalDayDialogBinding = null
        }
        fiscalDayDialog?.show()
        refreshFiscalDayStatus()
    }

    private fun fiscalDayStatusLabel(status: String?): String {
        return when (status) {
            "FiscalDayOpened" -> getString(R.string.fiscal_day_status_open)
            "FiscalDayClosed" -> getString(R.string.fiscal_day_status_closed)
            "FiscalDayCloseFailed" -> getString(R.string.fiscal_day_status_close_failed)
            "FiscalDayCloseInitiated" -> getString(R.string.fiscal_day_status_closing)
            null, "" -> getString(R.string.fiscal_day_status_unknown)
            else -> status
        }
    }

    private fun renderFiscalDayDialog(status: FiscalDayStatus?, error: String = "") {
        val dialogBinding = fiscalDayDialogBinding ?: return
        val deviceId = status?.deviceId
        val branchName = status?.branchName ?: session.branchName.orEmpty()
        dialogBinding.fiscalDayBranchLabel.text = if (!deviceId.isNullOrBlank()) {
            getString(R.string.fiscal_day_branch_device, branchName, deviceId)
        } else {
            branchName
        }

        if (error.isNotBlank()) {
            dialogBinding.fiscalDayErrorLabel.visibility = View.VISIBLE
            dialogBinding.fiscalDayErrorLabel.text = error
            dialogBinding.fiscalDayStatusLabel.text = getString(R.string.fiscal_day_status_error)
            dialogBinding.fiscalDayStatusLabel.setTextColor(getColor(R.color.error))
        } else {
            dialogBinding.fiscalDayErrorLabel.visibility = View.GONE
            dialogBinding.fiscalDayStatusLabel.text = fiscalDayStatusLabel(status?.fiscalDayStatus)
            dialogBinding.fiscalDayStatusLabel.setTextColor(
                when (status?.fiscalDayStatus) {
                    "FiscalDayOpened" -> getColor(R.color.status_ready)
                    "FiscalDayCloseFailed" -> getColor(R.color.error)
                    else -> getColor(R.color.text_primary)
                },
            )
        }

        dialogBinding.fiscalDayNumberLabel.text =
            status?.fiscalDayNumber?.toString()?.takeIf { it.isNotBlank() && it != "null" } ?: "—"
        dialogBinding.fiscalDayGlobalNoLabel.text =
            status?.lastReceiptGlobalNo?.toString()?.takeIf { it.isNotBlank() && it != "null" } ?: "—"

        val busyError = error.isNotBlank()
        dialogBinding.fiscalDayRefreshButton.isEnabled = true
        dialogBinding.fiscalDayOpenButton.isEnabled = !busyError && status?.canOpenDay == true
        dialogBinding.fiscalDayCloseDayButton.isEnabled = !busyError && status?.canCloseDay == true
    }

    private fun setFiscalDayButtonsEnabled(enabled: Boolean) {
        val dialogBinding = fiscalDayDialogBinding ?: return
        dialogBinding.fiscalDayRefreshButton.isEnabled = enabled
        if (!enabled) {
            dialogBinding.fiscalDayOpenButton.isEnabled = false
            dialogBinding.fiscalDayCloseDayButton.isEnabled = false
        }
    }

    private fun refreshFiscalDayStatus() {
        if (!session.fiscalizationEnabled) return
        lifecycleScope.launch {
            setFiscalDayButtonsEnabled(false)
            try {
                fiscalDayStatus = withContext(Dispatchers.IO) { api.fetchFiscalDayStatus() }
                renderFiscalDayDialog(fiscalDayStatus)
            } catch (err: ApiException) {
                fiscalDayStatus = null
                renderFiscalDayDialog(null, err.message ?: getString(R.string.fiscal_day_status_error))
                handleApiError(err)
            } catch (err: Exception) {
                fiscalDayStatus = null
                val message = getString(R.string.connection_failed, err.message ?: "")
                renderFiscalDayDialog(null, message)
                showError(message)
            }
        }
    }

    private fun runFiscalDayAction(open: Boolean) {
        if (!session.fiscalizationEnabled) return
        lifecycleScope.launch {
            setFiscalDayButtonsEnabled(false)
            try {
                fiscalDayStatus = withContext(Dispatchers.IO) {
                    if (open) api.openFiscalDay() else api.closeFiscalDay()
                }
                renderFiscalDayDialog(fiscalDayStatus)
                Toast.makeText(
                    this@PosActivity,
                    if (open) R.string.fiscal_day_opened else R.string.fiscal_day_close_requested,
                    Toast.LENGTH_SHORT,
                ).show()
                if (!open) {
                    delay(2500)
                    if (fiscalDayDialog != null) {
                        refreshFiscalDayStatus()
                    }
                }
            } catch (err: ApiException) {
                handleApiError(err)
                refreshFiscalDayStatus()
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message ?: ""))
                refreshFiscalDayStatus()
            }
        }
    }

    private fun openFiscalInvoicesDialog() {
        if (!session.fiscalizationEnabled) {
            Toast.makeText(this, R.string.fiscal_day_not_configured, Toast.LENGTH_LONG).show()
            return
        }
        val dialogBinding = DialogFiscalInvoicesBinding.inflate(layoutInflater)
        fiscalInvoicesDialogBinding = dialogBinding
        val date = todayIso()
        dialogBinding.fiscalInvoicesDateLabel.text = getString(R.string.fiscal_invoices_date, date)

        val adapter = FiscalInvoiceAdapter(
            canApprove = session.canApproveFiscalReceipt,
            onApprove = ::approveFiscalInvoice,
            onReprint = ::reprintFiscalInvoice,
        )
        fiscalInvoiceAdapter = adapter
        dialogBinding.fiscalInvoiceList.layoutManager = LinearLayoutManager(this)
        dialogBinding.fiscalInvoiceList.adapter = adapter
        dialogBinding.fiscalInvoicesRefreshButton.setOnClickListener { loadTodaysFiscalInvoices() }

        fiscalInvoicesDialog = MaterialAlertDialogBuilder(this)
            .setTitle(R.string.fiscal_invoices_title)
            .setView(dialogBinding.root)
            .setNegativeButton(android.R.string.cancel, null)
            .create()
        fiscalInvoicesDialog?.setOnDismissListener {
            fiscalInvoicesDialog = null
            fiscalInvoicesDialogBinding = null
            fiscalInvoiceAdapter = null
        }
        fiscalInvoicesDialog?.show()
        loadTodaysFiscalInvoices()
    }

    private fun loadTodaysFiscalInvoices() {
        val dialogBinding = fiscalInvoicesDialogBinding ?: return
        lifecycleScope.launch {
            dialogBinding.fiscalInvoicesRefreshButton.isEnabled = false
            binding.refreshProgress.visibility = View.VISIBLE
            try {
                val date = todayIso()
                dialogBinding.fiscalInvoicesDateLabel.text =
                    getString(R.string.fiscal_invoices_date, date)
                val orders = withContext(Dispatchers.IO) { api.fetchTodaysFiscalInvoices(date) }
                    .sortedWith(
                        compareBy<KitchenOrder> {
                            when (it.fiscal_approval_status) {
                                "pending", "failed" -> 0
                                "approved" -> 1
                                else -> 2
                            }
                        }.thenByDescending { it.id },
                    )
                fiscalInvoiceAdapter?.submitList(orders)
                dialogBinding.fiscalInvoiceEmptyLabel.visibility =
                    if (orders.isEmpty()) View.VISIBLE else View.GONE
                dialogBinding.fiscalInvoiceList.visibility =
                    if (orders.isEmpty()) View.GONE else View.VISIBLE
            } catch (err: ApiException) {
                handleApiError(err)
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message ?: ""))
            } finally {
                dialogBinding.fiscalInvoicesRefreshButton.isEnabled = true
                binding.refreshProgress.visibility = View.GONE
            }
        }
    }

    private fun approveFiscalInvoice(order: KitchenOrder) {
        if (!session.canApproveFiscalReceipt) return
        lifecycleScope.launch {
            Toast.makeText(this@PosActivity, R.string.fiscal_invoice_approving, Toast.LENGTH_SHORT).show()
            binding.refreshProgress.visibility = View.VISIBLE
            try {
                val updated = withContext(Dispatchers.IO) { api.approveFiscalReceipt(order.id) }
                Toast.makeText(
                    this@PosActivity,
                    R.string.fiscal_invoice_approved,
                    Toast.LENGTH_SHORT,
                ).show()
                if (updated.fiscal?.qrPayload().isNullOrBlank()) {
                    Toast.makeText(
                        this@PosActivity,
                        R.string.fiscal_invoice_approved_no_qr,
                        Toast.LENGTH_LONG,
                    ).show()
                }
                printReceipt(updated)
                loadTodaysFiscalInvoices()
            } catch (err: ApiException) {
                handleApiError(err)
                loadTodaysFiscalInvoices()
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message ?: ""))
            } finally {
                binding.refreshProgress.visibility = View.GONE
            }
        }
    }

    private fun reprintFiscalInvoice(order: KitchenOrder) {
        lifecycleScope.launch {
            printReceipt(order)
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
                            openStockTake()
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
                            openStockTake()
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
        if (posMode == PosMode.ORDER) {
            renderCart()
        }
    }

    private fun existingOrdersForCurrentSelection(): List<KitchenOrder> {
        if (posMode != PosMode.ORDER) return emptyList()
        if (currentOrderType() != "dine_in") return emptyList()
        val table = selectedTableName?.trim().orEmpty()
        if (table.isEmpty()) return emptyList()
        return openOrdersForTable(table)
    }

    private fun renderExistingOrderPreview(orders: List<KitchenOrder>) {
        if (orders.isEmpty()) {
            binding.existingOrderLabel.visibility = View.GONE
            binding.existingOrderItems.visibility = View.GONE
            return
        }
        val lines = buildString {
            orders.forEachIndexed { index, order ->
                if (index > 0) append("\n\n")
                append("Order #${order.id}")
                if (orders.size > 1 && order.table_number.isNotBlank()) {
                    append(" · Table ${order.table_number}")
                }
                append(" · ${ProductAdapter.formatMoney(order.total_amount, baseCurrencySymbol())}")
                order.items.forEach { item ->
                    append('\n')
                    val qty = item.quantity.toDoubleOrNull() ?: 1.0
                    val qtyLabel = if (qty % 1.0 == 0.0) qty.toInt().toString() else item.quantity
                    append("  $qtyLabel× ${item.product_name}")
                    val addonNames = item.addons.map { it.name }.filter { it.isNotBlank() }
                    if (addonNames.isNotEmpty()) {
                        append(" (${addonNames.joinToString(", ")})")
                    }
                    if (item.notes.isNotBlank()) {
                        append(" — Note: ${item.notes}")
                    }
                }
            }
        }
        binding.existingOrderLabel.visibility = View.VISIBLE
        binding.existingOrderItems.visibility = View.VISIBLE
        binding.existingOrderItems.text = lines
    }

    private fun occupiedTableNames(orders: List<KitchenOrder>): Set<String> {
        return orders.filter { order ->
            order.status == "open" &&
                order.order_type == "dine_in" &&
                order.table_number.isNotBlank()
        }.map { it.table_number }.toSet()
    }

    private fun openOrdersForTable(tableNumber: String): List<KitchenOrder> {
        val table = tableNumber.trim()
        if (table.isEmpty()) return emptyList()
        return openOrders.filter {
            it.status == "open" && it.order_type == "dine_in" && it.table_number == table
        }
    }

    private fun receiptOrders(): List<KitchenOrder> {
        val order = selectedOrder ?: return emptyList()
        if (order.status == "unpaid") return listOf(order)
        val tableOrders = openOrdersForTable(order.table_number)
        return if (tableOrders.size > 1) tableOrders else listOf(order)
    }

    private fun receiptInclusiveTotal(): Double {
        return receiptOrders().sumOf { it.total_amount.toDoubleOrNull() ?: 0.0 }
    }

    private fun openTablePicker(purpose: TablePickerPurpose = TablePickerPurpose.SELECT) {
        tablePickerPurpose = purpose
        lifecycleScope.launch {
            binding.refreshProgress.visibility = View.VISIBLE
            try {
                val (tables, orders) = withContext(Dispatchers.IO) {
                    Pair(api.fetchDiningTables(), api.fetchPayableOrders())
                }
                diningTables = tables.filter { it.is_active }.sortedBy { it.sort_order }
                openOrders = orders
                showTablePickerDialog(diningTables, occupiedTableNames(orders), purpose)
            } catch (err: ApiException) {
                handleApiError(err)
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message ?: ""))
            } finally {
                binding.refreshProgress.visibility = View.GONE
            }
        }
    }

    private fun showTablePickerDialog(
        tables: List<DiningTable>,
        occupied: Set<String>,
        purpose: TablePickerPurpose,
    ) {
        val dialogBinding = DialogTablePickerBinding.inflate(layoutInflater)
        val sourceTable = if (purpose == TablePickerPurpose.TRANSFER) {
            selectedOrder?.table_number?.trim().orEmpty()
        } else {
            ""
        }
        val disabledNames = if (sourceTable.isNotEmpty()) setOf(sourceTable) else emptySet()
        val adapter = DiningTableAdapter(
            occupiedNames = occupied,
            selectedName = if (purpose == TablePickerPurpose.SELECT) selectedTableName else null,
            disabledNames = disabledNames,
            onTableClick = { table ->
                tablePickerDialog?.dismiss()
                if (purpose == TablePickerPurpose.TRANSFER) {
                    confirmTransferToTable(table.name)
                } else {
                    setSelectedTable(table.name)
                }
            },
        )
        dialogBinding.tableGrid.layoutManager = GridLayoutManager(this, 3)
        dialogBinding.tableGrid.adapter = adapter
        adapter.submitList(tables)
        dialogBinding.tablePickerHint.setText(
            if (purpose == TablePickerPurpose.TRANSFER) {
                R.string.transfer_table_hint
            } else {
                R.string.table_picker_hint
            },
        )

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

        val titleRes = if (purpose == TablePickerPurpose.TRANSFER) {
            R.string.transfer_table_title
        } else {
            R.string.select_table_title
        }
        tablePickerDialog = MaterialAlertDialogBuilder(this)
            .setTitle(titleRes)
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
        binding.customerPaymentButton.visibility = if (showReceipt) View.VISIBLE else View.GONE
        if (!showReceipt && posMode == PosMode.RECEIPT) {
            setPosMode(PosMode.ORDER)
        }
    }

    private fun showMoreMenu() {
        val popup = PopupMenu(this, binding.moreMenuButton)
        popup.menuInflater.inflate(R.menu.pos_overflow, popup.menu)

        val showReceiptActions = session.canCollectPayment
        val showFiscalDay = session.canManageFiscalDay && session.fiscalizationEnabled
        val showFiscalInvoices = session.fiscalizationEnabled &&
            (session.canApproveFiscalReceipt || session.canManageFiscalDay)

        popup.menu.findItem(R.id.menu_fiscal_day)?.isVisible = showFiscalDay
        popup.menu.findItem(R.id.menu_fiscal_invoices)?.isVisible = showFiscalInvoices
        popup.menu.findItem(R.id.menu_day_end)?.isVisible = showReceiptActions
        popup.menu.findItem(R.id.menu_stock_take)?.isVisible = showReceiptActions
        popup.menu.findItem(R.id.menu_grv)?.isVisible = session.canAccessGrv
        popup.menu.findItem(R.id.menu_expense)?.isVisible = showReceiptActions

        popup.setOnMenuItemClickListener { item ->
            handleMoreMenuItem(item)
        }
        popup.show()
    }

    private fun handleMoreMenuItem(item: MenuItem): Boolean {
        when (item.itemId) {
            R.id.menu_fiscal_day -> openFiscalDayDialog()
            R.id.menu_fiscal_invoices -> openFiscalInvoicesDialog()
            R.id.menu_day_end -> openDayEndDialog()
            R.id.menu_stock_take -> openStockTake()
            R.id.menu_grv -> startActivity(Intent(this, GrvActivity::class.java))
            R.id.menu_expense -> openExpenseDialog()
            R.id.menu_settings -> startActivity(Intent(this, SettingsActivity::class.java))
            else -> return false
        }
        return true
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
        binding.customerInput.setOnClickListener {
            openCustomerPickerDialog(
                includeWalkIn = true,
                onSelected = { customer ->
                    selectedAccountCustomer = customer
                    binding.customerInput.setText(
                        customer?.let(::customerLabel)
                            ?: getString(R.string.customer_walk_in),
                    )
                    updateAccountBalanceHint()
                    updateReceiptCheckoutState()
                    linkSelectedCustomerToOrder()
                },
            )
        }
        binding.customerInputLayout.setEndIconOnClickListener {
            binding.customerInput.performClick()
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

    private fun setupCustomerSearch(preselectCustomerId: Int? = null) {
        selectedAccountCustomer = customers.firstOrNull { it.id == preselectCustomerId }
        binding.customerInput.setText(
            selectedAccountCustomer?.let(::customerLabel)
                ?: getString(R.string.customer_walk_in),
        )
    }

    private fun openCustomerPickerDialog(
        includeWalkIn: Boolean = true,
        onSelected: (Customer?) -> Unit,
    ) {
        val dialogBinding = DialogCustomerPickerBinding.inflate(layoutInflater)
        val walkInLabel = getString(R.string.customer_walk_in)
        val allChoices = mutableListOf<CustomerPaymentChoice<Customer?>>()
        if (includeWalkIn) {
            allChoices.add(CustomerPaymentChoice(walkInLabel, null))
        }
        allChoices.addAll(
            customers.map { customer ->
                CustomerPaymentChoice(customerLabel(customer), customer)
            },
        )
        val visibleChoices = allChoices.toMutableList()
        val adapter = ArrayAdapter(
            this,
            android.R.layout.simple_list_item_1,
            visibleChoices,
        )
        dialogBinding.customerPickerList.adapter = adapter

        fun refreshList(query: String) {
            val needle = query.trim().lowercase(Locale.getDefault())
            visibleChoices.clear()
            if (needle.isEmpty()) {
                visibleChoices.addAll(allChoices)
            } else {
                visibleChoices.addAll(
                    allChoices.filter { choice ->
                        choice.label.lowercase(Locale.getDefault()).contains(needle)
                    },
                )
            }
            adapter.notifyDataSetChanged()
            val empty = visibleChoices.isEmpty()
            dialogBinding.customerPickerList.visibility = if (empty) View.GONE else View.VISIBLE
            dialogBinding.customerPickerEmptyLabel.visibility = if (empty) View.VISIBLE else View.GONE
        }

        dialogBinding.customerPickerSearchInput.doAfterTextChanged { text ->
            refreshList(text?.toString().orEmpty())
        }

        customerPickerDialog?.dismiss()
        customerPickerDialog = MaterialAlertDialogBuilder(this)
            .setTitle(R.string.select_customer_title)
            .setView(dialogBinding.root)
            .setNegativeButton(android.R.string.cancel, null)
            .create()

        dialogBinding.customerPickerList.setOnItemClickListener { _, _, position, _ ->
            val choice = visibleChoices.getOrNull(position) ?: return@setOnItemClickListener
            onSelected(choice.value)
            customerPickerDialog?.dismiss()
        }

        customerPickerDialog?.show()
        dialogBinding.customerPickerSearchInput.requestFocus()
        customerPickerDialog?.window?.setSoftInputMode(
            android.view.WindowManager.LayoutParams.SOFT_INPUT_STATE_VISIBLE or
                android.view.WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE,
        )
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
        return selectedAccountCustomer
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
        binding.moreMenuButton.setOnClickListener { showMoreMenu() }
        binding.customerPaymentButton.setOnClickListener { openCustomerPaymentDialog() }
        binding.logoutButton.setOnClickListener {
            refreshJob?.cancel()
            session.clearLogin()
            startActivity(Intent(this, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            })
            finish()
        }
        binding.clearButton.setOnClickListener {
            if (posMode == PosMode.ORDER) {
                cart.clear()
                renderCart()
            }
        }
        binding.transferItemsButton.setOnClickListener {
            startItemTransfer()
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
            selectedTransferKeys.clear()
            receiptAdapter.selectedOrderId = null
            binding.panelTitle.text = getString(R.string.collect_payment)
            binding.checkoutButton.text = getString(R.string.collect_payment)
            binding.transferItemsButton.visibility = View.GONE
            binding.clearButton.visibility = View.GONE
            loadOpenOrders()
            startReceiptRefresh()
        } else {
            refreshJob?.cancel()
            selectedOrder = null
            selectedTransferKeys.clear()
            binding.panelTitle.text = getString(R.string.current_order)
            binding.checkoutButton.text = getString(R.string.place_order)
            binding.transferItemsButton.visibility = View.GONE
            binding.clearButton.visibility = View.VISIBLE
            syncOrderTypeUi(if (binding.orderTypeSpinner.selectedItemPosition == 1) "dine_in" else "takeaway")
            loadOpenOrders()
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
                // Products/categories/currencies must render even if customers fails.
                // Customers are only needed for account payment / customer deposit.
                val catalog = withContext(Dispatchers.IO) {
                    PosCatalog(
                        products = api.fetchProducts(),
                        categories = api.fetchCategories(),
                        currencies = api.fetchCurrencies(),
                    )
                }
                products = catalog.products
                allCurrencies = catalog.currencies
                currencies = catalog.currencies.filter {
                    it.is_active && (it.is_base || !it.current_rate.isNullOrBlank())
                }
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
                if (products.isEmpty()) {
                    showError(getString(R.string.pos_no_products))
                }
            } catch (err: ApiException) {
                handleApiError(err)
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message ?: ""))
            } finally {
                binding.refreshProgress.visibility = View.GONE
            }
            loadCustomersQuietly()
        }
    }

    private fun loadCustomersQuietly() {
        lifecycleScope.launch {
            try {
                customers = withContext(Dispatchers.IO) { api.fetchCustomers() }
            } catch (_: Exception) {
                // Non-fatal: products already shown; account payment can refresh later.
            }
        }
    }

    private fun usableCurrencies(): List<Currency> {
        return currencies
            .filter { it.is_base || !it.current_rate.isNullOrBlank() }
            .sortedByDescending { it.is_base }
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

    private fun loadOpenOrders(silent: Boolean = false, selectOrderId: Int? = null) {
        lifecycleScope.launch {
            if (!silent) binding.refreshProgress.visibility = View.VISIBLE
            try {
                val orders = withContext(Dispatchers.IO) { api.fetchPayableOrders() }
                    .sortedByDescending { it.created_at }
                openOrders = orders
                receiptAdapter.openOrders = orders
                receiptAdapter.submitList(orders)
                selectedOrder = when {
                    selectOrderId != null -> orders.find { it.id == selectOrderId }
                    else -> selectedOrder?.let { current ->
                        orders.find { it.id == current.id }
                    }
                }
                receiptAdapter.selectedOrderId = selectedOrder?.id
                if (selectedOrder == null) {
                    binding.paymentSection.visibility = View.GONE
                }
                if (posMode == PosMode.RECEIPT) {
                    renderReceiptPanel()
                } else if (posMode == PosMode.ORDER) {
                    renderCart()
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
        selectedTransferKeys.clear()
        binding.cartList.adapter = cartAdapter
        val existingOrders = existingOrdersForCurrentSelection()
        renderExistingOrderPreview(existingOrders)
        val primaryExisting = existingOrders.firstOrNull()
        binding.panelTitle.text = when {
            primaryExisting == null -> getString(R.string.current_order)
            existingOrders.size > 1 -> "Table ${selectedTableName.orEmpty()} — ${existingOrders.size} orders"
            else -> "Order #${primaryExisting.id}"
        }
        binding.checkoutButton.text = if (existingOrders.isNotEmpty()) {
            getString(R.string.add_to_order)
        } else {
            getString(R.string.place_order)
        }
        val lines = cart.values.toList()
        cartAdapter.submitList(lines)
        val hasLines = lines.isNotEmpty()
        val emptyHint = if (existingOrders.isNotEmpty()) {
            getString(R.string.tap_products_add_more)
        } else {
            getString(R.string.tap_products_hint)
        }
        binding.emptyCartLabel.text = emptyHint
        binding.emptyCartLabel.visibility = if (hasLines) View.GONE else View.VISIBLE
        binding.cartList.visibility = if (hasLines) View.VISIBLE else View.GONE
        binding.clearButton.visibility = View.VISIBLE
        binding.clearButton.isEnabled = hasLines
        binding.checkoutButton.isEnabled = hasLines
        binding.transferItemsButton.visibility = View.GONE
        val total = lines.sumOf { it.price * it.quantity }
        binding.totalCaption.setText(
            if (existingOrders.isNotEmpty()) R.string.adding_now else R.string.total,
        )
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
        binding.existingOrderLabel.visibility = View.GONE
        binding.existingOrderItems.visibility = View.GONE
        val order = selectedOrder
        if (order == null) {
            receiptPaymentOrderId = null
            selectedTransferKeys.clear()
            binding.cartList.adapter = cartAdapter
            cartAdapter.submitList(emptyList())
            binding.emptyCartLabel.visibility = View.VISIBLE
            binding.cartList.visibility = View.GONE
            binding.paymentSection.visibility = View.GONE
            binding.clearButton.visibility = View.GONE
            binding.checkoutButton.isEnabled = false
            binding.transferItemsButton.visibility = View.GONE
            binding.totalCaption.setText(R.string.total)
            binding.totalLabel.text = ProductAdapter.formatMoney(0.0, baseCurrencySymbol())
            binding.exchangeRateLabel.visibility = View.GONE
            return
        }

        val orderChanged = receiptPaymentOrderId != order.id
        receiptPaymentOrderId = order.id
        if (orderChanged) selectedTransferKeys.clear()

        val canTransferItems = order.status == "open" && (
            order.order_type == "dine_in" || order.order_type == "takeaway"
            )
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
                    orderId = if (canTransferItems) tableOrder.id else null,
                    orderItemId = if (canTransferItems) item.id else null,
                )
            }
        }
        binding.cartList.adapter = receiptCartAdapter
        receiptCartAdapter.removable = false
        receiptCartAdapter.transferable = canTransferItems
        receiptCartAdapter.selectedTransferKeys = selectedTransferKeys.toSet()
        receiptCartAdapter.submitList(lines)
        binding.emptyCartLabel.visibility = View.GONE
        binding.cartList.visibility = View.VISIBLE
        binding.paymentSection.visibility = View.VISIBLE
        binding.clearButton.visibility = View.GONE
        updateTransferButtonState(canTransferItems)
        if (orderChanged) {
            paymentMethod = PaymentMethod.CASH
            binding.paymentMethodToggle.check(binding.cashPaymentButton.id)
            setupCustomerSearch(order.customer)
            binding.splitPaymentEnabled.isChecked = false
            clearSplitPaymentInputs()
            // Always start collect-payment on the base currency; user can change if needed.
            selectedCurrencyId = usableCurrencies().firstOrNull { it.is_base }?.id
        }
        syncPaymentMethodUi()
        renderCurrencyButtons()
        updateReceiptCheckoutState()
    }

    private fun updateTransferButtonState(canTransfer: Boolean? = null) {
        val order = selectedOrder
        val transferable = canTransfer ?: (
            order?.status == "open" && (
                order.order_type == "dine_in" || order.order_type == "takeaway"
                )
            )
        binding.transferItemsButton.visibility = if (transferable) View.VISIBLE else View.GONE
        binding.transferItemsButton.isEnabled = transferable && selectedTransferKeys.isNotEmpty()
        binding.transferItemsButton.text = if (selectedTransferKeys.isNotEmpty()) {
            getString(R.string.transfer_lines_count, selectedTransferKeys.size)
        } else {
            getString(R.string.transfer_action)
        }
        receiptCartAdapter.selectedTransferKeys = selectedTransferKeys.toSet()
    }

    private fun startItemTransfer() {
        if (selectedTransferKeys.isEmpty()) {
            Toast.makeText(this, R.string.transfer_select_items, Toast.LENGTH_SHORT).show()
            return
        }
        val order = selectedOrder
        if (order == null || order.status != "open") {
            Toast.makeText(this, R.string.transfer_select_items, Toast.LENGTH_SHORT).show()
            return
        }
        if (order.order_type != "dine_in" && order.order_type != "takeaway") {
            Toast.makeText(this, R.string.transfer_select_items, Toast.LENGTH_SHORT).show()
            return
        }
        val options = arrayOf(
            getString(R.string.transfer_destination_table),
            getString(R.string.transfer_destination_takeaway),
        )
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.transfer_destination_title)
            .setItems(options) { _, which ->
                when (which) {
                    0 -> openTablePicker(TablePickerPurpose.TRANSFER)
                    1 -> openOrderPickerForTransfer()
                }
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun openOrderPickerForTransfer() {
        lifecycleScope.launch {
            binding.refreshProgress.visibility = View.VISIBLE
            try {
                val orders = withContext(Dispatchers.IO) { api.fetchPayableOrders() }
                openOrders = orders
                showOrderPickerDialog(orders)
            } catch (err: ApiException) {
                handleApiError(err)
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message ?: ""))
            } finally {
                binding.refreshProgress.visibility = View.GONE
            }
        }
    }

    private fun showOrderPickerDialog(orders: List<KitchenOrder>) {
        val sourceIds = receiptOrders().map { it.id }.toSet()
        val candidates = orders.filter {
            it.status == "open"
                && it.order_type == "takeaway"
                && it.id !in sourceIds
        }
        showTakeawayOrderPicker(
            candidates = candidates,
            titleRes = R.string.transfer_order_title,
            hintRes = R.string.transfer_order_hint,
            newOrderLabelRes = R.string.transfer_new_order,
            emptyLabelRes = R.string.transfer_no_other_orders,
            onPick = { orderId ->
                confirmTransferToOrder(
                    orderId,
                    if (orderId == null) {
                        getString(R.string.transfer_new_order)
                    } else {
                        orders.firstOrNull { it.id == orderId }?.receiptHeaderLabel()
                            ?: "#$orderId"
                    },
                )
            },
        )
    }

    private fun showTakeawayOrderPicker(
        candidates: List<KitchenOrder>,
        titleRes: Int,
        hintRes: Int,
        newOrderLabelRes: Int,
        emptyLabelRes: Int,
        onPick: (Int?) -> Unit,
        onCancel: (() -> Unit)? = null,
    ) {
        var settled = false
        fun settlePick(orderId: Int?) {
            if (settled) return
            settled = true
            orderPickerDialog?.dismiss()
            onPick(orderId)
        }
        fun settleCancel() {
            if (settled) return
            settled = true
            onCancel?.invoke()
        }
        val dialogBinding = DialogOrderPickerBinding.inflate(layoutInflater)
        dialogBinding.orderPickerHint.setText(hintRes)
        dialogBinding.newOrderButton.setText(newOrderLabelRes)
        dialogBinding.orderEmptyLabel.setText(emptyLabelRes)
        val adapter = ReceiptOrderAdapter(
            onOrderClick = { order -> settlePick(order.id) },
        )
        dialogBinding.orderList.layoutManager = LinearLayoutManager(this)
        dialogBinding.orderList.adapter = adapter
        adapter.submitList(candidates)
        dialogBinding.orderEmptyLabel.visibility =
            if (candidates.isEmpty()) View.VISIBLE else View.GONE
        dialogBinding.orderList.visibility =
            if (candidates.isEmpty()) View.GONE else View.VISIBLE
        dialogBinding.newOrderButton.setOnClickListener {
            settlePick(null)
        }
        orderPickerDialog = MaterialAlertDialogBuilder(this)
            .setTitle(titleRes)
            .setView(dialogBinding.root)
            .setNegativeButton(android.R.string.cancel) { _, _ ->
                settleCancel()
            }
            .setOnCancelListener {
                settleCancel()
            }
            .create()
        orderPickerDialog?.show()
    }

    private suspend fun chooseTakeawayDestinationForPlace(): TakeawayPick {
        binding.refreshProgress.visibility = View.VISIBLE
        val orders = try {
            withContext(Dispatchers.IO) { api.fetchPayableOrders() }.also { openOrders = it }
        } catch (err: ApiException) {
            handleApiError(err)
            return TakeawayPick.Cancelled
        } catch (err: Exception) {
            showError(getString(R.string.connection_failed, err.message ?: ""))
            return TakeawayPick.Cancelled
        } finally {
            binding.refreshProgress.visibility = View.GONE
        }
        val candidates = orders.filter {
            it.status == "open" && it.order_type == "takeaway"
        }
        if (candidates.isEmpty()) return TakeawayPick.NewOrder

        return suspendCancellableCoroutine { cont ->
            showTakeawayOrderPicker(
                candidates = candidates,
                titleRes = R.string.place_takeaway_title,
                hintRes = R.string.place_takeaway_hint,
                newOrderLabelRes = R.string.place_takeaway_new,
                emptyLabelRes = R.string.transfer_no_other_orders,
                onPick = { orderId ->
                    if (cont.isActive) {
                        cont.resume(
                            if (orderId == null) TakeawayPick.NewOrder
                            else TakeawayPick.Existing(orderId),
                        )
                    }
                },
                onCancel = {
                    if (cont.isActive) cont.resume(TakeawayPick.Cancelled)
                },
            )
            cont.invokeOnCancellation {
                orderPickerDialog?.dismiss()
            }
        }
    }

    private fun confirmTransferToOrder(destinationOrderId: Int?, destinationLabel: String) {
        val lineCount = selectedTransferKeys.size
        if (lineCount == 0) {
            Toast.makeText(this, R.string.transfer_select_items, Toast.LENGTH_SHORT).show()
            return
        }
        val message = if (destinationOrderId == null) {
            getString(R.string.transfer_confirm_new_order, lineCount)
        } else {
            getString(R.string.transfer_confirm_order, lineCount, destinationLabel)
        }
        MaterialAlertDialogBuilder(this)
            .setMessage(message)
            .setPositiveButton(R.string.transfer_action) { _, _ ->
                performTransfer(
                    destinationOrderId = destinationOrderId,
                    destinationOrderType = "takeaway",
                )
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun confirmTransferToTable(destinationTable: String) {
        val lineCount = selectedTransferKeys.size
        if (lineCount == 0) {
            Toast.makeText(this, R.string.transfer_select_items, Toast.LENGTH_SHORT).show()
            return
        }
        MaterialAlertDialogBuilder(this)
            .setMessage(getString(R.string.transfer_confirm, lineCount, destinationTable))
            .setPositiveButton(R.string.transfer_action) { _, _ ->
                performTransfer(
                    destinationTable = destinationTable,
                    destinationOrderType = "dine_in",
                )
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun performTransfer(
        destinationTable: String? = null,
        destinationOrderId: Int? = null,
        destinationOrderType: String? = null,
    ) {
        val groups = linkedMapOf<Int, MutableList<Int>>()
        for (line in receiptCartAdapter.currentList) {
            if (line.lineKey !in selectedTransferKeys) continue
            val orderId = line.orderId ?: continue
            val itemId = line.orderItemId ?: continue
            groups.getOrPut(orderId) { mutableListOf() }.add(itemId)
        }
        if (groups.isEmpty()) {
            Toast.makeText(this, R.string.transfer_select_items, Toast.LENGTH_SHORT).show()
            return
        }

        binding.transferItemsButton.isEnabled = false
        lifecycleScope.launch {
            binding.refreshProgress.visibility = View.VISIBLE
            try {
                var resultDestinationId = destinationOrderId
                withContext(Dispatchers.IO) {
                    for ((orderId, itemIds) in groups) {
                        val result = api.transferOrderItems(
                            orderId = orderId,
                            itemIds = itemIds,
                            tableNumber = destinationTable,
                            destinationOrderId = destinationOrderId,
                            destinationOrderType = destinationOrderType,
                        )
                        resultDestinationId = result.destinationOrder.id
                    }
                }
                selectedTransferKeys.clear()
                val toastRes = when {
                    destinationTable != null -> getString(R.string.transfer_success, destinationTable)
                    destinationOrderId != null -> getString(R.string.transfer_success_order, destinationOrderId)
                    else -> getString(R.string.transfer_success_new_order)
                }
                Toast.makeText(this@PosActivity, toastRes, Toast.LENGTH_SHORT).show()
                loadOpenOrders(selectOrderId = resultDestinationId)
            } catch (err: ApiException) {
                handleApiError(err)
                updateTransferButtonState()
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message ?: ""))
                updateTransferButtonState()
            } finally {
                binding.refreshProgress.visibility = View.GONE
            }
        }
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
        if (!session.canCollectPayment) {
            promptWaiterAccessCode { accessCode ->
                if (accessCode != null) {
                    placeOrderWithAccessCode(accessCode)
                }
            }
            return
        }
        placeOrderWithAccessCode(null)
    }

    private fun promptWaiterAccessCode(onResult: (String?) -> Unit) {
        val input = TextInputEditText(this).apply {
            inputType = android.text.InputType.TYPE_CLASS_NUMBER
            hint = getString(R.string.access_code_hint)
            filters = arrayOf(android.text.InputFilter.LengthFilter(4))
        }
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val pad = (16 * resources.displayMetrics.density).toInt()
            setPadding(pad, pad / 2, pad, 0)
            addView(input)
        }
        var settled = false
        fun finish(code: String?) {
            if (settled) return
            settled = true
            onResult(code)
        }
        val dialog = MaterialAlertDialogBuilder(this)
            .setTitle(R.string.access_code_place_order_title)
            .setMessage(R.string.access_code_place_order_message)
            .setView(container)
            .setNegativeButton(android.R.string.cancel) { _, _ -> finish(null) }
            .setPositiveButton(android.R.string.ok) { _, _ ->
                val code = input.text?.toString()?.trim().orEmpty()
                if (!code.matches(Regex("^\\d{4}$"))) {
                    Toast.makeText(this, R.string.access_code_invalid, Toast.LENGTH_SHORT).show()
                    finish(null)
                } else {
                    finish(code)
                }
            }
            .setOnCancelListener { finish(null) }
            .create()
        input.doAfterTextChanged { editable ->
            val code = editable?.toString()?.trim().orEmpty()
            if (code.matches(Regex("^\\d{4}$")) && dialog.isShowing) {
                dialog.dismiss()
                finish(code)
            }
        }
        dialog.show()
        input.requestFocus()
    }

    private fun placeOrderWithAccessCode(accessCode: String?) {
        binding.checkoutButton.isEnabled = false
        lifecycleScope.launch {
            try {
                val orderType = currentOrderType()
                var existingOrderId: Int? = null
                if (orderType == "takeaway") {
                    when (val pick = chooseTakeawayDestinationForPlace()) {
                        TakeawayPick.Cancelled -> {
                            renderCart()
                            return@launch
                        }
                        TakeawayPick.NewOrder -> existingOrderId = null
                        is TakeawayPick.Existing -> existingOrderId = pick.orderId
                    }
                }
                val tableNumber = if (orderType == "dine_in") selectedTableName else null
                val existingTableOrderId = tableNumber?.trim()?.takeIf { it.isNotEmpty() }?.let { table ->
                    openOrdersForTable(table).firstOrNull()?.id
                }
                val order = withContext(Dispatchers.IO) {
                    api.createOrder(
                        orderType,
                        tableNumber,
                        cart.values.toList(),
                        existingOrderId = existingOrderId,
                        accessCode = accessCode,
                    )
                }
                cart.clear()
                if (orderType == "dine_in") {
                    setSelectedTable(null)
                }
                renderCart()
                loadOpenOrders(silent = true)
                val addedToExisting = (existingOrderId != null && order.id == existingOrderId) ||
                    (existingTableOrderId != null && order.id == existingTableOrderId)
                // Adding to an open order: kitchen/bar tablets print only the new lines.
                // Do not reprint the full POS order slip.
                if (!addedToExisting) {
                    printOrderTicket(order)
                }
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
        errorHideJob?.cancel()
        errorHideJob = lifecycleScope.launch {
            delay(ERROR_BANNER_MS)
            binding.errorBanner.visibility = View.GONE
        }
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

    private suspend fun printOrderTicket(
        order: KitchenOrder,
        documentTitle: String = "Order ticket",
    ) {
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
            documentTitle = documentTitle,
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

    private enum class TablePickerPurpose {
        SELECT,
        TRANSFER,
    }

    private data class PosCatalog(
        val products: List<Product>,
        val categories: List<com.cafedeparis.kitchen.data.ProductCategory>,
        val currencies: List<Currency>,
    )

    companion object {
        private const val RECEIPT_REFRESH_MS = 10_000L
        private const val ERROR_BANNER_MS = 6_000L
    }
}
