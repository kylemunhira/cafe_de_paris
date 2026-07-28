package com.cafedeparis.kitchen

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.GridLayoutManager
import com.cafedeparis.kitchen.data.ApiClient
import com.cafedeparis.kitchen.data.ApiException
import com.cafedeparis.kitchen.data.AppConfig
import com.cafedeparis.kitchen.data.KitchenOrder
import com.cafedeparis.kitchen.data.OrderItem
import com.cafedeparis.kitchen.data.SessionManager
import com.cafedeparis.kitchen.databinding.ActivityMainBinding
import com.cafedeparis.kitchen.print.EscPosPrinter
import com.cafedeparis.kitchen.print.PrinterException
import com.cafedeparis.kitchen.ui.OrderAdapter
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

class MainActivity : KeepScreenOnActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var session: SessionManager
    private lateinit var config: AppConfig
    private lateinit var api: ApiClient
    private val adapter = OrderAdapter()
    private var pollJob: Job? = null
    private var errorHideJob: Job? = null
    private var lastOpenOrderIds: Set<Int> = emptySet()
    private val printer = EscPosPrinter()

    private val bluetoothPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (!granted) {
            Toast.makeText(this, R.string.bluetooth_permission_required, Toast.LENGTH_LONG).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        session = SessionManager(this)
        config = AppConfig(this)
        api = ApiClient(session, config)

        binding.ordersList.layoutManager = GridLayoutManager(this, 2)
        binding.ordersList.adapter = adapter

        binding.loginButton.setOnClickListener { attemptLogin() }
        binding.logoutButton.setOnClickListener { logout() }
        binding.settingsButton.setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }
        binding.retryButton.setOnClickListener { refreshOrders(manual = true) }

        if (session.isLoggedIn) {
            routeAfterLogin()
        } else {
            showLogin()
        }
    }

    override fun onResume() {
        super.onResume()
        config.reload()
        if (session.isLoggedIn) {
            if (session.canAccessBakery) {
                openBakeryAndFinish()
            } else if (session.shouldOpenPos()) {
                openPosAndFinish()
            } else {
                refreshOrders(manual = true)
            }
        } else {
            showLogin()
        }
    }

    override fun onDestroy() {
        pollJob?.cancel()
        errorHideJob?.cancel()
        super.onDestroy()
    }

    private fun attemptLogin() {
        val username = binding.usernameInput.text?.toString()?.trim().orEmpty()
        val password = binding.passwordInput.text?.toString().orEmpty()

        if (username.isBlank() || password.isBlank()) {
            Toast.makeText(this, R.string.login_fields_required, Toast.LENGTH_SHORT).show()
            return
        }
        binding.loginButton.isEnabled = false
        binding.loginProgress.visibility = View.VISIBLE
        binding.loginError.visibility = View.GONE

        lifecycleScope.launch {
            try {
                val response = withContext(Dispatchers.IO) {
                    api.login(username, password)
                }
                session.saveLogin(response)
                binding.passwordInput.text?.clear()
                routeAfterLogin()
                requestBluetoothIfNeeded()
            } catch (err: ApiException) {
                binding.loginError.text = err.message
                binding.loginError.visibility = View.VISIBLE
            } catch (err: Exception) {
                binding.loginError.text = getString(R.string.connection_failed, err.message ?: "")
                binding.loginError.visibility = View.VISIBLE
            } finally {
                binding.loginButton.isEnabled = true
                binding.loginProgress.visibility = View.GONE
            }
        }
    }

    private fun routeAfterLogin() {
        if (session.canAccessBakery) {
            openBakeryAndFinish()
            return
        }
        if (session.shouldOpenPos()) {
            openPosAndFinish()
            return
        }
        if (!session.canAccessKitchen) {
            binding.loginError.text = getString(R.string.login_not_allowed)
            binding.loginError.visibility = View.VISIBLE
            session.clearLogin()
            showLogin()
            return
        }
        showKitchen()
        startPolling()
    }

    private fun openPosAndFinish() {
        startActivity(Intent(this, PosActivity::class.java))
        finish()
    }

    private fun openBakeryAndFinish() {
        startActivity(Intent(this, BakeryProductionActivity::class.java))
        finish()
    }

    private fun logout() {
        pollJob?.cancel()
        session.clearLogin()
        session.clearCancellationTracking()
        lastOpenOrderIds = emptySet()
        adapter.submitList(emptyList())
        showLogin()
    }

    private fun showLogin() {
        binding.loginPanel.visibility = View.VISIBLE
        binding.kitchenPanel.visibility = View.GONE
    }

    private fun showKitchen() {
        binding.loginPanel.visibility = View.GONE
        binding.kitchenPanel.visibility = View.VISIBLE
        binding.branchLabel.text = getString(R.string.branch_label, session.branchName ?: "")
        val stationLabel = session.kitchenStationDisplay
        binding.staffLabel.text = if (stationLabel.isNullOrBlank()) {
            session.displayName ?: ""
        } else {
            "${session.displayName ?: ""} · $stationLabel"
        }
        session.ensureCancellationPollSince(currentIsoTimestamp())
        updateStatus(getString(R.string.status_waiting))
    }

    private fun startPolling() {
        pollJob?.cancel()
        pollJob = lifecycleScope.launch {
            while (isActive) {
                refreshOrders(manual = false)
                delay(POLL_INTERVAL_MS)
            }
        }
    }

    private fun refreshOrders(manual: Boolean) {
        if (!session.isLoggedIn) return

        lifecycleScope.launch {
            if (manual) {
                binding.refreshProgress.visibility = View.VISIBLE
            }
            try {
                val cancelled = withContext(Dispatchers.IO) {
                    val since = session.cancellationPollSince
                    if (since.isNullOrBlank()) emptyList() else api.fetchCancelledOrders(since)
                }
                session.cancellationPollSince = currentIsoTimestamp()

                val orders = withContext(Dispatchers.IO) { api.fetchOpenOrders() }
                    .sortedBy { it.created_at }
                adapter.submitList(orders)
                binding.emptyState.visibility = if (orders.isEmpty()) View.VISIBLE else View.GONE
                binding.errorBanner.visibility = View.GONE
                updateStatus(getString(R.string.status_live, orders.size))
                processKitchenPrinting(orders, cancelled)
            } catch (err: ApiException) {
                if (err.statusCode == 401) {
                    Toast.makeText(this@MainActivity, R.string.session_expired, Toast.LENGTH_LONG).show()
                    logout()
                } else {
                    showError(err.message ?: getString(R.string.load_failed))
                }
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message ?: ""))
            } finally {
                binding.refreshProgress.visibility = View.GONE
            }
        }
    }

    private suspend fun processKitchenPrinting(
        orders: List<KitchenOrder>,
        cancelledOrders: List<KitchenOrder>,
    ) {
        val printerAddress = session.printerAddress ?: return

        val currentIds = orders.map { it.id }.toSet()
        val disappeared = lastOpenOrderIds - currentIds
        lastOpenOrderIds = currentIds

        val cancelledIds = cancelledOrders.map { it.id }.toSet()
        val printedCancelIds = session.getPrintedCancelOrderIds().toMutableSet()

        // Freeze printed item snapshots before any updates so transfer
        // source/destination can still be resolved in this poll.
        val snapshotByOrder = linkedMapOf<Int, List<OrderItem>>()
        for (orderId in (currentIds + disappeared + cancelledIds)) {
            val snapshot = session.getPrintedItemSnapshot(orderId)
            if (snapshot.isNotEmpty()) {
                snapshotByOrder[orderId] = snapshot
            }
        }

        for (order in cancelledOrders) {
            if (order.id in printedCancelIds) continue
            val items = order.items.ifEmpty { snapshotByOrder[order.id].orEmpty() }
            if (items.isEmpty()) continue
            val transferredTo = findDestinationOrderId(items, orders, excludeOrderId = order.id)
            if (!printCancelTicket(
                    printerAddress,
                    order.copy(items = items),
                    partial = false,
                    transferredToOrderId = transferredTo,
                )
            ) {
                return
            }
            session.markCancelPrinted(order.id)
            printedCancelIds.add(order.id)
            session.removePrintedItemSnapshot(order.id)
            session.markPrinted(order.id, SessionManager.orderPrintFingerprint(order.copy(items = items)))
        }

        for (orderId in disappeared) {
            if (orderId in printedCancelIds || orderId in cancelledIds) continue
            val snapshot = snapshotByOrder[orderId].orEmpty()
            if (snapshot.isEmpty()) continue
            val remote = withContext(Dispatchers.IO) {
                runCatching { api.fetchOrder(orderId) }.getOrNull()
            }
            session.removePrintedItemSnapshot(orderId)
            if (remote?.status != "cancelled") continue
            val transferredTo = findDestinationOrderId(snapshot, orders, excludeOrderId = orderId)
            if (!printCancelTicket(
                    printerAddress,
                    remote.copy(items = snapshot),
                    partial = false,
                    transferredToOrderId = transferredTo,
                )
            ) {
                return
            }
            session.markCancelPrinted(orderId)
            printedCancelIds.add(orderId)
        }

        val fingerprints = session.getPrintedOrderFingerprints().toMutableMap()
        for (order in orders) {
            if (order.items.isEmpty()) continue

            val snapshot = snapshotByOrder[order.id].orEmpty()
            val removedItems = computeRemovedItems(snapshot, order)
            if (removedItems.isNotEmpty()) {
                val transferredTo = findDestinationOrderId(removedItems, orders, excludeOrderId = order.id)
                if (!printCancelTicket(
                        printerAddress,
                        order.copy(items = removedItems),
                        partial = true,
                        transferredToOrderId = transferredTo,
                    )
                ) {
                    return
                }
            }

            val fingerprint = SessionManager.orderPrintFingerprint(order)
            val previous = fingerprints[order.id]
            if (previous == fingerprint) {
                session.setPrintedItemSnapshot(order.id, order.items)
                continue
            }

            if (previous == SessionManager.LEGACY_PRINT_FINGERPRINT) {
                session.markPrinted(order.id, fingerprint)
                fingerprints[order.id] = fingerprint
                session.setPrintedItemSnapshot(order.id, order.items)
                continue
            }

            val previousKeys = previous
                ?.split("|")
                ?.filter { it.isNotBlank() }
                ?.toSet()
                .orEmpty()
            val newItems = if (previousKeys.isEmpty()) {
                order.items
            } else {
                order.items.filter { item ->
                    "${item.id}:${item.quantity}" !in previousKeys
                }
            }

            if (newItems.isNotEmpty()) {
                val ticket = if (previousKeys.isEmpty()) {
                    order
                } else {
                    order.copy(items = newItems)
                }
                val transferredFrom = findSourceOrderId(
                    newItems,
                    snapshotByOrder,
                    excludeOrderId = order.id,
                )
                val printAsUpdate = previousKeys.isNotEmpty()
                if (!printOrderTicket(
                        printerAddress,
                        ticket,
                        isUpdate = printAsUpdate,
                        transferredFromOrderId = transferredFrom,
                    )
                ) {
                    return
                }
            }

            session.markPrinted(order.id, fingerprint)
            fingerprints[order.id] = fingerprint
            session.setPrintedItemSnapshot(order.id, order.items)
        }
    }

    private suspend fun printOrderTicket(
        printerAddress: String,
        order: KitchenOrder,
        isUpdate: Boolean,
        transferredFromOrderId: Int? = null,
    ): Boolean {
        return try {
            withContext(Dispatchers.IO) {
                printer.printOrder(
                    printerAddress,
                    order,
                    isUpdate = isUpdate,
                    transferredFromOrderId = transferredFromOrderId,
                )
            }
            true
        } catch (err: PrinterException) {
            withContext(Dispatchers.Main) {
                showError(getString(R.string.print_failed, err.message ?: ""))
            }
            false
        } catch (err: SecurityException) {
            withContext(Dispatchers.Main) {
                requestBluetoothIfNeeded()
                showError(getString(R.string.bluetooth_permission_required))
            }
            false
        } catch (err: Exception) {
            withContext(Dispatchers.Main) {
                showError(getString(R.string.print_failed, err.message ?: ""))
            }
            false
        }
    }

    private suspend fun printCancelTicket(
        printerAddress: String,
        order: KitchenOrder,
        partial: Boolean,
        transferredToOrderId: Int? = null,
    ): Boolean {
        return try {
            withContext(Dispatchers.IO) {
                printer.printCancelOrder(
                    printerAddress,
                    order,
                    partial = partial,
                    transferredToOrderId = transferredToOrderId,
                )
            }
            true
        } catch (err: PrinterException) {
            withContext(Dispatchers.Main) {
                showError(getString(R.string.print_failed, err.message ?: ""))
            }
            false
        } catch (err: SecurityException) {
            withContext(Dispatchers.Main) {
                requestBluetoothIfNeeded()
                showError(getString(R.string.bluetooth_permission_required))
            }
            false
        } catch (err: Exception) {
            withContext(Dispatchers.Main) {
                showError(getString(R.string.print_failed, err.message ?: ""))
            }
            false
        }
    }

    private fun findDestinationOrderId(
        items: List<OrderItem>,
        openOrders: List<KitchenOrder>,
        excludeOrderId: Int,
    ): Int? {
        val itemIds = items.map { it.id }.toSet()
        if (itemIds.isEmpty()) return null
        val matches = openOrders.filter { order ->
            order.id != excludeOrderId && order.items.any { it.id in itemIds }
        }
        return matches.singleOrNull()?.id
            ?: matches.maxByOrNull { order -> order.items.count { it.id in itemIds } }?.id
    }

    private fun findSourceOrderId(
        items: List<OrderItem>,
        snapshotByOrder: Map<Int, List<OrderItem>>,
        excludeOrderId: Int,
    ): Int? {
        val itemIds = items.map { it.id }.toSet()
        if (itemIds.isEmpty()) return null
        var bestOrderId: Int? = null
        var bestCount = 0
        for ((orderId, snapshot) in snapshotByOrder) {
            if (orderId == excludeOrderId) continue
            val count = itemIds.count { id -> snapshot.any { it.id == id } }
            if (count > bestCount) {
                bestCount = count
                bestOrderId = orderId
            }
        }
        return bestOrderId?.takeIf { bestCount > 0 }
    }

    private fun computeRemovedItems(snapshot: List<OrderItem>, order: KitchenOrder): List<OrderItem> {
        if (snapshot.isEmpty()) return emptyList()
        val currentById = order.items.associateBy { it.id }
        val removed = mutableListOf<OrderItem>()
        for (prev in snapshot) {
            val current = currentById[prev.id]
            if (current == null) {
                removed.add(prev)
                continue
            }
            val prevQty = prev.quantity.toDoubleOrNull() ?: 0.0
            val curQty = current.quantity.toDoubleOrNull() ?: 0.0
            if (prevQty > curQty + 0.0001) {
                val diffQty = prevQty - curQty
                val qtyStr = if (diffQty % 1.0 == 0.0) {
                    diffQty.toInt().toString()
                } else {
                    String.format(Locale.US, "%.2f", diffQty)
                }
                removed.add(prev.copy(quantity = qtyStr))
            }
        }
        return removed
    }

    private fun currentIsoTimestamp(): String {
        return SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US).apply {
            timeZone = TimeZone.getDefault()
        }.format(Date())
    }

    private fun showError(message: String) {
        binding.errorBanner.text = message
        binding.errorBanner.visibility = View.VISIBLE
        updateStatus(message)
        errorHideJob?.cancel()
        errorHideJob = lifecycleScope.launch {
            delay(ERROR_BANNER_MS)
            binding.errorBanner.visibility = View.GONE
        }
    }

    private fun updateStatus(message: String) {
        binding.statusLabel.text = message
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

    companion object {
        private const val POLL_INTERVAL_MS = 5_000L
        private const val ERROR_BANNER_MS = 6_000L
    }
}
