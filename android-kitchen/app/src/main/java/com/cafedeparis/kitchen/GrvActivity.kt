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
import com.cafedeparis.kitchen.data.DeliveryNote
import com.cafedeparis.kitchen.data.SessionManager
import com.cafedeparis.kitchen.databinding.ActivityGrvBinding
import com.cafedeparis.kitchen.print.EscPosPrinter
import com.cafedeparis.kitchen.print.PrinterException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.DecimalFormat

class GrvActivity : KeepScreenOnActivity() {

    private lateinit var binding: ActivityGrvBinding
    private lateinit var session: SessionManager
    private lateinit var api: ApiClient
    private val printer = EscPosPrinter()
    private var allNotes: List<DeliveryNote> = emptyList()
    private var loading = false
    private var filterReady = false
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
        binding = ActivityGrvBinding.inflate(layoutInflater)
        setContentView(binding.root)
        session = SessionManager(this)
        api = ApiClient(session, AppConfig(this))
        if (!session.isLoggedIn || !session.canAccessGrv) {
            Toast.makeText(this, R.string.grv_access_denied, Toast.LENGTH_LONG).show()
            finish()
            return
        }

        binding.branchLabel.text = getString(
            R.string.grv_branch_label,
            session.branchName.orEmpty(),
        )
        binding.staffLabel.text = session.displayName.orEmpty()
        binding.backButton.setOnClickListener { finish() }
        binding.refreshButton.setOnClickListener { loadNotes() }
        binding.settingsButton.setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }
        binding.logoutButton.setOnClickListener { logout() }
        configureFilter()
        loadNotes()
    }

    private fun configureFilter() {
        val labels = listOf(
            getString(R.string.grv_filter_incoming),
            getString(R.string.grv_filter_requested),
            getString(R.string.grv_filter_dispatched),
            getString(R.string.grv_filter_delivered),
            getString(R.string.grv_filter_all),
        )
        binding.filterSpinner.adapter = ArrayAdapter(
            this,
            android.R.layout.simple_spinner_item,
            labels,
        ).also {
            it.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        }
        binding.filterSpinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(
                parent: AdapterView<*>?,
                view: View?,
                position: Int,
                id: Long,
            ) {
                if (filterReady) renderNotes()
            }

            override fun onNothingSelected(parent: AdapterView<*>?) = Unit
        }
        filterReady = true
    }

    private fun selectedFilter(): String {
        return FILTER_KEYS.getOrNull(binding.filterSpinner.selectedItemPosition) ?: "incoming"
    }

    private fun loadNotes() {
        if (loading) return
        loading = true
        showLoading(true)
        binding.errorBanner.visibility = View.GONE
        lifecycleScope.launch {
            try {
                allNotes = withContext(Dispatchers.IO) { api.fetchIncomingDeliveryNotes() }
                renderStats()
                renderNotes()
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

    private fun renderStats() {
        binding.statNotApproved.text = allNotes.count { it.status == "requested" }.toString()
        binding.statAwaiting.text = allNotes.count { it.status == "dispatched" }.toString()
        binding.statReceived.text = allNotes.count { it.status == "delivered" }.toString()
    }

    private fun filteredNotes(): List<DeliveryNote> {
        return when (selectedFilter()) {
            "incoming" -> allNotes.filter { it.status in INCOMING_STATUSES }
            "all" -> allNotes
            else -> allNotes.filter { it.status == selectedFilter() }
        }
    }

    private fun renderNotes() {
        binding.notesList.removeAllViews()
        val notes = filteredNotes()
        if (notes.isEmpty()) {
            addEmptyText(emptyMessage())
            return
        }
        notes.forEach { note ->
            val card = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(8, 12, 8, 12)
            }
            card.addView(TextView(this).apply {
                text = getString(
                    R.string.grv_note_title,
                    grvNumber(note.id),
                    note.sourceName,
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
                    R.string.grv_note_meta,
                    formatQuantity(note.totalQuantity),
                    note.status.replaceFirstChar { it.uppercase() },
                    formatDate(note.createdAt),
                )
                setTextColor(getColor(R.color.text_muted))
            })
            val actions = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                setPadding(0, 8, 0, 0)
            }
            actions.addView(Button(this).apply {
                text = getString(R.string.grv_print)
                setOnClickListener { printGrv(note) }
            })
            when (note.status) {
                "requested" -> actions.addView(Button(this).apply {
                    text = getString(R.string.grv_approve)
                    setOnClickListener { confirmApprove(note) }
                })
                "dispatched" -> actions.addView(Button(this).apply {
                    text = getString(R.string.grv_confirm_receipt)
                    setOnClickListener { confirmDeliver(note) }
                })
            }
            card.addView(actions)
            binding.notesList.addView(card)
            binding.notesList.addView(
                View(this).apply { setBackgroundColor(getColor(R.color.background)) },
                LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 2),
            )
        }
    }

    private fun emptyMessage(): String {
        return when (selectedFilter()) {
            "incoming" -> getString(R.string.grv_empty_incoming)
            "requested" -> getString(R.string.grv_empty_requested)
            "dispatched" -> getString(R.string.grv_empty_dispatched)
            "delivered" -> getString(R.string.grv_empty_delivered)
            else -> getString(R.string.grv_empty_all)
        }
    }

    private fun addEmptyText(message: String) {
        binding.notesList.addView(TextView(this).apply {
            text = message
            setTextColor(getColor(R.color.text_muted))
            setPadding(0, 16, 0, 16)
        })
    }

    private fun confirmApprove(note: DeliveryNote) {
        AlertDialog.Builder(this)
            .setTitle(R.string.grv_approve)
            .setMessage(getString(R.string.grv_approve_confirm, grvNumber(note.id)))
            .setNegativeButton(android.R.string.cancel, null)
            .setPositiveButton(R.string.grv_approve) { _, _ -> approveNote(note) }
            .show()
    }

    private fun confirmDeliver(note: DeliveryNote) {
        AlertDialog.Builder(this)
            .setTitle(R.string.grv_confirm_receipt)
            .setMessage(getString(R.string.grv_deliver_confirm, grvNumber(note.id)))
            .setNegativeButton(android.R.string.cancel, null)
            .setPositiveButton(R.string.grv_confirm_receipt) { _, _ -> deliverNote(note) }
            .show()
    }

    private fun approveNote(note: DeliveryNote) {
        showLoading(true)
        lifecycleScope.launch {
            try {
                val updated = withContext(Dispatchers.IO) { api.approveDeliveryNote(note.id) }
                replaceNote(updated)
                val message = if (updated.status == "delivered") {
                    getString(R.string.grv_received, grvNumber(updated.id))
                } else {
                    getString(R.string.grv_approved, grvNumber(updated.id))
                }
                Toast.makeText(this@GrvActivity, message, Toast.LENGTH_SHORT).show()
            } catch (err: ApiException) {
                handleApiError(err)
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message.orEmpty()))
            } finally {
                showLoading(false)
            }
        }
    }

    private fun deliverNote(note: DeliveryNote) {
        showLoading(true)
        lifecycleScope.launch {
            try {
                val updated = withContext(Dispatchers.IO) { api.deliverDeliveryNote(note.id) }
                replaceNote(updated)
                Toast.makeText(
                    this@GrvActivity,
                    getString(R.string.grv_received, grvNumber(updated.id)),
                    Toast.LENGTH_SHORT,
                ).show()
            } catch (err: ApiException) {
                handleApiError(err)
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message.orEmpty()))
            } finally {
                showLoading(false)
            }
        }
    }

    private fun replaceNote(updated: DeliveryNote) {
        allNotes = allNotes.map { if (it.id == updated.id) updated else it }
        renderStats()
        renderNotes()
    }

    private fun printGrv(note: DeliveryNote) {
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
                Toast.makeText(this@GrvActivity, R.string.grv_printed, Toast.LENGTH_SHORT).show()
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

    private fun grvNumber(id: Int): String = id.toString().padStart(5, '0')

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
            showError(err.message ?: getString(R.string.grv_load_failed))
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
        startActivity(
            Intent(this, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            },
        )
        finish()
    }

    companion object {
        private val INCOMING_STATUSES = setOf("requested", "approved", "dispatched")
        private val FILTER_KEYS = listOf("incoming", "requested", "dispatched", "delivered", "all")
        private const val ERROR_BANNER_MS = 6_000L
    }
}
