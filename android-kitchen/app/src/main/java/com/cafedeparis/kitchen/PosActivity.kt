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
import android.widget.GridLayout
import android.widget.Toast
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
import com.cafedeparis.kitchen.data.Product
import com.cafedeparis.kitchen.data.SessionManager
import com.cafedeparis.kitchen.databinding.ActivityPosBinding
import com.cafedeparis.kitchen.databinding.DialogDayEndBinding
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
import java.util.Locale
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
    private var currencies: List<Currency> = emptyList()
    private var customers: List<Customer> = emptyList()
    private var diningTables: List<DiningTable> = emptyList()
    private var openOrders: List<KitchenOrder> = emptyList()
    private var selectedOrder: KitchenOrder? = null
    private var selectedTableName: String? = null
    private var activeCategoryId: Int? = null
    private var searchQuery: String = ""
    private var posMode: PosMode = PosMode.ORDER
    private var paymentMethod: PaymentMethod = PaymentMethod.CASH
    private var selectedCurrencyId: Int? = null
    private var tablePickerDialog: androidx.appcompat.app.AlertDialog? = null
    private var dayEndDialog: androidx.appcompat.app.AlertDialog? = null
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

        loadCatalog()
        setPosMode(PosMode.ORDER)
        requestBluetoothIfNeeded()
    }

    override fun onDestroy() {
        refreshJob?.cancel()
        tablePickerDialog?.dismiss()
        dayEndDialog?.dismiss()
        super.onDestroy()
    }

    private fun todayIso(): String {
        return SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date())
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
                        .setPositiveButton(android.R.string.ok, null)
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
        val countedInputs = linkedMapOf<Int, TextInputEditText>()
        for (currency in activeCurrencies) {
            val label = if (currency.is_base) {
                currency.name
            } else {
                val symbol = currency.symbol.takeIf { it.isNotBlank() }?.let { " ($it)" }.orEmpty()
                "${currency.name}$symbol"
            }
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
            }
            fieldLayout.addView(input)
            dialogBinding.dayEndCurrencyFields.addView(fieldLayout)
            countedInputs[currency.id] = input
        }

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

    private fun printDayEndReport(
        dialogBinding: DialogDayEndBinding,
        countedInputs: Map<Int, TextInputEditText>,
    ) {
        val reportDate = dialogBinding.dayEndDateInput.text?.toString()?.trim().orEmpty()
            .ifBlank { todayIso() }
        val counted = linkedMapOf<Int, String>()
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
            counted[currencyId] = String.format(Locale.US, "%.2f", amount)
        }

        lifecycleScope.launch {
            binding.refreshProgress.visibility = View.VISIBLE
            try {
                val check = withContext(Dispatchers.IO) { api.checkDayEndStockTake(reportDate) }
                if (!check.completed) {
                    MaterialAlertDialogBuilder(this@PosActivity)
                        .setTitle(R.string.day_end_stock_take_required)
                        .setMessage(check.detail)
                        .setPositiveButton(android.R.string.ok, null)
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
                        .setPositiveButton(android.R.string.ok, null)
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
            setPosMode(if (checkedId == binding.receiptModeButton.id) PosMode.RECEIPT else PosMode.ORDER)
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
    }

    private fun syncPaymentMethodUi() {
        val isAccount = paymentMethod == PaymentMethod.ACCOUNT
        binding.customerGroup.visibility = if (isAccount) View.VISIBLE else View.GONE
        binding.currencyGroup.visibility = if (isAccount) View.GONE else View.VISIBLE
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
        val balance = customer.account_balance.toDoubleOrNull() ?: 0.0
        val balanceSuffix = if (balance > 0) {
            " · ${ProductAdapter.formatMoney(customer.account_balance)}"
        } else {
            ""
        }
        return customer.full_name + balanceSuffix
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
            ProductAdapter.formatMoney(customer.account_balance),
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
        binding.checkoutButton.isEnabled = when (paymentMethod) {
            PaymentMethod.ACCOUNT -> {
                val customer = selectedCustomer()
                val total = order.total_amount.toDoubleOrNull() ?: 0.0
                val balance = customer?.account_balance?.toDoubleOrNull() ?: 0.0
                customer != null && balance >= total
            }
            PaymentMethod.CASH -> selectedCurrency() != null
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
        binding.dayEndButton.setOnClickListener { openDayEndDialog() }
        binding.clearButton.setOnClickListener {
            if (posMode == PosMode.ORDER) {
                cart.clear()
                renderCart()
            }
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
        posMode = mode
        binding.orderModePanel.visibility = if (mode == PosMode.ORDER) View.VISIBLE else View.GONE
        binding.receiptModePanel.visibility = if (mode == PosMode.RECEIPT) View.VISIBLE else View.GONE
        binding.paymentSection.visibility = if (mode == PosMode.RECEIPT && selectedOrder != null) View.VISIBLE else View.GONE

        if (mode == PosMode.RECEIPT) {
            selectedOrder = null
            receiptAdapter.selectedOrderId = null
            binding.panelTitle.text = getString(R.string.collect_payment)
            binding.checkoutButton.text = getString(R.string.collect_payment)
            loadOpenOrders()
            startReceiptRefresh()
        } else {
            refreshJob?.cancel()
            selectedOrder = null
            binding.panelTitle.text = getString(R.string.current_order)
            binding.checkoutButton.text = getString(R.string.place_order)
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
        val total = lines.sumOf { it.price * it.quantity }
        binding.totalLabel.text = ProductAdapter.formatMoney(total.toString())
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
            binding.cartList.adapter = cartAdapter
            cartAdapter.submitList(emptyList())
            binding.emptyCartLabel.visibility = View.VISIBLE
            binding.cartList.visibility = View.GONE
            binding.paymentSection.visibility = View.GONE
            binding.clearButton.isEnabled = false
            binding.checkoutButton.isEnabled = false
            binding.totalLabel.text = ProductAdapter.formatMoney("0")
            return
        }

        val lines = order.items.map { item ->
            val qty = item.quantity.toDoubleOrNull() ?: 1.0
            val price = item.price.toDoubleOrNull() ?: 0.0
            val addonPrice = item.addons.sumOf { it.price.toDoubleOrNull() ?: 0.0 }
            CartLine(
                lineKey = "order-${item.id}",
                productId = item.id,
                name = item.product_name,
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
        binding.cartList.adapter = receiptCartAdapter
        receiptCartAdapter.submitList(lines)
        binding.emptyCartLabel.visibility = View.GONE
        binding.cartList.visibility = View.VISIBLE
        binding.paymentSection.visibility = View.VISIBLE
        binding.clearButton.isEnabled = false
        paymentMethod = PaymentMethod.CASH
        binding.paymentMethodToggle.check(binding.cashPaymentButton.id)
        setupCustomerSpinner(order.customer)
        syncPaymentMethodUi()
        renderCurrencyButtons()
        updateReceiptCheckoutState()
        binding.totalLabel.text = ProductAdapter.formatMoney(order.total_amount)
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
                val order = withContext(Dispatchers.IO) {
                    api.createOrder(currentOrderType(), tableNumber, cart.values.toList())
                }
                cart.clear()
                setSelectedTable(null)
                renderCart()
                printOrderTicket(order)
                Toast.makeText(
                    this@PosActivity,
                    getString(R.string.order_placed, order.id, ProductAdapter.formatMoney(order.total_amount)),
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

        if (paymentMethod == PaymentMethod.ACCOUNT) {
            val customer = selectedCustomer()
            if (customer == null) {
                Toast.makeText(this, R.string.select_customer_account, Toast.LENGTH_SHORT).show()
                return
            }
            val total = order.total_amount.toDoubleOrNull() ?: 0.0
            val balance = customer.account_balance.toDoubleOrNull() ?: 0.0
            if (balance < total) {
                Toast.makeText(
                    this,
                    getString(
                        R.string.insufficient_account_balance,
                        ProductAdapter.formatMoney(customer.account_balance),
                    ),
                    Toast.LENGTH_LONG,
                ).show()
                return
            }
        } else {
            if (selectedCurrency() == null) {
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
                        api.payOrderCash(order.id, selectedCurrency()!!.id)
                    }
                }
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
                        ProductAdapter.formatMoney(paid.total_amount),
                    )
                } else {
                    getString(
                        R.string.order_paid,
                        paid.id,
                        paid.payment_currency_name ?: selectedCurrency()?.name.orEmpty(),
                        paid.amount_paid ?: paid.total_amount,
                    )
                }
                Toast.makeText(this@PosActivity, message, Toast.LENGTH_LONG).show()
                selectedOrder = null
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

    private suspend fun printOrderTicket(order: KitchenOrder) {
        val printerAddress = session.printerAddress
        if (printerAddress.isNullOrBlank()) {
            withContext(Dispatchers.Main) {
                Toast.makeText(this@PosActivity, R.string.printer_not_configured, Toast.LENGTH_SHORT).show()
            }
            return
        }

        val baseCurrency = currencies.firstOrNull { it.is_base }
        val options = OrderSlipPrintOptions(
            baseCurrencyCode = baseCurrency?.code?.takeIf { it.isNotBlank() }
                ?: baseCurrency?.name,
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

        try {
            withContext(Dispatchers.IO) {
                printer.printReceipt(printerAddress, order)
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
