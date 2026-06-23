package com.cafedeparis.kitchen

import android.Manifest
import android.bluetooth.BluetoothAdapter
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.widget.ArrayAdapter
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.cafedeparis.kitchen.data.AppConfig
import com.cafedeparis.kitchen.data.SessionManager
import com.cafedeparis.kitchen.databinding.ActivitySettingsBinding

class SettingsActivity : AppCompatActivity() {

    private lateinit var binding: ActivitySettingsBinding
    private lateinit var session: SessionManager
    private lateinit var config: AppConfig

    private val bluetoothPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            loadPairedPrinters()
        } else {
            Toast.makeText(this, R.string.bluetooth_permission_required, Toast.LENGTH_LONG).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySettingsBinding.inflate(layoutInflater)
        setContentView(binding.root)

        session = SessionManager(this)
        config = AppConfig(this)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        title = getString(R.string.settings_title)

        binding.configServerLabel.text = getString(R.string.config_server_label, config.serverUrl)
        binding.configPathLabel.text = getString(R.string.config_path_label, config.configFile.absolutePath)
        binding.printerAddressInput.setText(session.printerAddress.orEmpty())

        binding.saveButton.setOnClickListener {
            session.printerAddress = binding.printerAddressInput.text?.toString()?.trim()
            Toast.makeText(this, R.string.settings_saved, Toast.LENGTH_SHORT).show()
            finish()
        }

        binding.refreshPrintersButton.setOnClickListener {
            ensureBluetoothPermission { loadPairedPrinters() }
        }

        ensureBluetoothPermission { loadPairedPrinters() }
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }

    private fun ensureBluetoothPermission(onGranted: () -> Unit) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) {
            onGranted()
            return
        }
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_CONNECT)
            == PackageManager.PERMISSION_GRANTED
        ) {
            onGranted()
        } else {
            bluetoothPermissionLauncher.launch(Manifest.permission.BLUETOOTH_CONNECT)
        }
    }

    private fun loadPairedPrinters() {
        val adapter = BluetoothAdapter.getDefaultAdapter()
        if (adapter == null || !adapter.isEnabled) {
            binding.pairedPrintersLabel.text = getString(R.string.bluetooth_off)
            return
        }

        val devices = try {
            adapter.bondedDevices?.toList().orEmpty()
        } catch (_: SecurityException) {
            emptyList()
        }

        if (devices.isEmpty()) {
            binding.pairedPrintersLabel.text = getString(R.string.no_paired_printers)
            return
        }

        val labels = devices.map { "${it.name} (${it.address})" }
        binding.pairedPrintersLabel.text = getString(R.string.tap_printer_hint)
        val listAdapter = ArrayAdapter(this, android.R.layout.simple_list_item_1, labels)
        binding.pairedPrintersList.adapter = listAdapter
        binding.pairedPrintersList.setOnItemClickListener { _, _, position, _ ->
            val device = devices[position]
            binding.printerAddressInput.setText(device.address)
        }
    }
}
