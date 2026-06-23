package com.cafedeparis.kitchen

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.GridLayoutManager
import com.cafedeparis.kitchen.data.ApiClient
import com.cafedeparis.kitchen.data.ApiException
import com.cafedeparis.kitchen.data.AppConfig
import com.cafedeparis.kitchen.data.KitchenOrder
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

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var session: SessionManager
    private lateinit var config: AppConfig
    private lateinit var api: ApiClient
    private val adapter = OrderAdapter()
    private var pollJob: Job? = null
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
            showKitchen()
            startPolling()
        } else {
            showLogin()
        }
    }

    override fun onResume() {
        super.onResume()
        config.reload()
        if (session.isLoggedIn) {
            refreshOrders(manual = true)
        } else {
            showLogin()
        }
    }

    override fun onDestroy() {
        pollJob?.cancel()
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
                showKitchen()
                startPolling()
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

    private fun logout() {
        pollJob?.cancel()
        session.clearLogin()
        adapter.submitList(emptyList())
        showLogin()
    }

    private fun showLogin() {
        binding.loginPanel.visibility = View.VISIBLE
        binding.kitchenPanel.visibility = View.GONE
        binding.configServerLabel.text = getString(R.string.config_server_label, config.serverUrl)
    }

    private fun showKitchen() {
        binding.loginPanel.visibility = View.GONE
        binding.kitchenPanel.visibility = View.VISIBLE
        binding.branchLabel.text = getString(R.string.branch_label, session.branchName ?: "")
        binding.staffLabel.text = session.displayName ?: ""
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
                val orders = withContext(Dispatchers.IO) { api.fetchOpenOrders() }
                    .sortedBy { it.created_at }
                adapter.submitList(orders)
                binding.emptyState.visibility = if (orders.isEmpty()) View.VISIBLE else View.GONE
                binding.errorBanner.visibility = View.GONE
                updateStatus(getString(R.string.status_live, orders.size))
                autoPrintNewOrders(orders)
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

    private suspend fun autoPrintNewOrders(orders: List<KitchenOrder>) {
        val printerAddress = session.printerAddress
        if (printerAddress.isNullOrBlank()) return

        val printedIds = session.getPrintedOrderIds().toMutableSet()
        val newOrders = orders.filter { it.id !in printedIds }
        if (newOrders.isEmpty()) return

        for (order in newOrders) {
            try {
                withContext(Dispatchers.IO) {
                    printer.printOrder(printerAddress, order)
                }
                session.markPrinted(order.id)
                printedIds.add(order.id)
            } catch (err: PrinterException) {
                withContext(Dispatchers.Main) {
                    showError(getString(R.string.print_failed, err.message ?: ""))
                }
                break
            } catch (err: SecurityException) {
                withContext(Dispatchers.Main) {
                    requestBluetoothIfNeeded()
                    showError(getString(R.string.bluetooth_permission_required))
                }
                break
            } catch (err: Exception) {
                withContext(Dispatchers.Main) {
                    showError(getString(R.string.print_failed, err.message ?: ""))
                }
                break
            }
        }
    }

    private fun showError(message: String) {
        binding.errorBanner.text = message
        binding.errorBanner.visibility = View.VISIBLE
        updateStatus(message)
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
    }
}
