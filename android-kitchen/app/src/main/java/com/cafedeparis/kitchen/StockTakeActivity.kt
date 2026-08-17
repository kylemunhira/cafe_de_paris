package com.cafedeparis.kitchen

import android.content.Intent
import android.os.Bundle
import android.text.InputType
import android.view.View
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.lifecycle.lifecycleScope
import com.cafedeparis.kitchen.data.ApiClient
import com.cafedeparis.kitchen.data.ApiException
import com.cafedeparis.kitchen.data.AppConfig
import com.cafedeparis.kitchen.data.SessionManager
import com.cafedeparis.kitchen.data.StockTake
import com.cafedeparis.kitchen.data.StockTakeLine
import com.cafedeparis.kitchen.data.StockTakeLineUpdate
import com.cafedeparis.kitchen.databinding.ActivityStockTakeBinding
import com.google.android.material.chip.Chip
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import java.text.DecimalFormat
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class StockTakeActivity : KeepScreenOnActivity() {

    private data class LineInputs(
        val lineId: Int,
        val counted: EditText,
        val wastage: EditText,
        val notes: EditText,
    )

    private lateinit var binding: ActivityStockTakeBinding
    private lateinit var session: SessionManager
    private lateinit var api: ApiClient

    private var allStockTakes: List<StockTake> = emptyList()
    private var activeStockTake: StockTake? = null
    private var historyFilter: String = "all"
    private var stationFilter: String = "all"
    private var lineInputs: MutableMap<Int, LineInputs> = linkedMapOf()
    private var loading = false
    private var errorHideJob: Job? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityStockTakeBinding.inflate(layoutInflater)
        setContentView(binding.root)
        session = SessionManager(this)
        api = ApiClient(session, AppConfig(this))

        if (!session.isLoggedIn || !session.canAccessPos) {
            Toast.makeText(this, R.string.stock_take_access_denied, Toast.LENGTH_LONG).show()
            finish()
            return
        }

        binding.branchLabel.text = getString(
            R.string.stock_take_branch_label,
            session.branchName.orEmpty(),
        )
        binding.staffLabel.text = session.displayName.orEmpty()
        binding.countDateInput.setText(todayIso())
        binding.backButton.setOnClickListener { finish() }
        binding.refreshButton.setOnClickListener { loadStockTakes(openDraft = false) }
        binding.settingsButton.setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }
        binding.logoutButton.setOnClickListener { logout() }
        binding.startDailyButton.setOnClickListener { startCount("daily") }
        binding.startMonthlyButton.setOnClickListener { startCount("monthly") }
        binding.saveButton.setOnClickListener { saveProgress(complete = false) }
        binding.completeButton.setOnClickListener { confirmComplete() }
        binding.cancelCountButton.setOnClickListener { confirmCancel() }
        binding.closeCountButton.setOnClickListener {
            activeStockTake = null
            renderActiveCount()
        }

        setupHistoryFilters()
        loadStockTakes(openDraft = true)
    }

    private fun setupHistoryFilters() {
        val filters = listOf(
            "all" to R.string.stock_take_filter_all,
            "daily" to R.string.stock_take_filter_daily,
            "monthly" to R.string.stock_take_filter_monthly,
            "draft" to R.string.stock_take_filter_draft,
            "completed" to R.string.stock_take_filter_completed,
        )
        binding.historyFilterChips.removeAllViews()
        filters.forEachIndexed { index, (key, labelRes) ->
            val chip = Chip(this).apply {
                text = getString(labelRes)
                isCheckable = true
                isChecked = index == 0
                setOnClickListener {
                    historyFilter = key
                    renderHistory()
                }
            }
            binding.historyFilterChips.addView(chip)
        }
    }

    private fun loadStockTakes(openDraft: Boolean) {
        if (loading) return
        loading = true
        showLoading(true)
        binding.errorBanner.visibility = View.GONE
        lifecycleScope.launch {
            try {
                allStockTakes = withContext(Dispatchers.IO) { api.fetchStockTakes() }
                renderHistory()
                val currentId = activeStockTake?.id
                if (currentId != null) {
                    val refreshed = allStockTakes.firstOrNull { it.id == currentId }
                    if (refreshed != null && refreshed.status != "cancelled") {
                        openStockTake(currentId)
                    } else {
                        activeStockTake = null
                        renderActiveCount()
                    }
                } else if (openDraft) {
                    val draft = allStockTakes.firstOrNull { it.status == "draft" }
                    if (draft != null) openStockTake(draft.id) else renderActiveCount()
                } else {
                    renderActiveCount()
                }
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

    private fun startCount(type: String) {
        val date = selectedDate()
        lifecycleScope.launch {
            showLoading(true)
            try {
                val created = withContext(Dispatchers.IO) {
                    api.createStockTake(type, date)
                }
                allStockTakes = withContext(Dispatchers.IO) { api.fetchStockTakes() }
                renderHistory()
                openStockTake(created.id)
            } catch (err: ApiException) {
                handleApiError(err)
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message.orEmpty()))
            } finally {
                showLoading(false)
            }
        }
    }

    private fun openStockTake(id: Int) {
        lifecycleScope.launch {
            showLoading(true)
            try {
                stationFilter = "all"
                activeStockTake = withContext(Dispatchers.IO) { api.fetchStockTake(id) }
                renderActiveCount()
            } catch (err: ApiException) {
                handleApiError(err)
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message.orEmpty()))
            } finally {
                showLoading(false)
            }
        }
    }

    private fun filteredHistory(): List<StockTake> {
        return when (historyFilter) {
            "daily" -> allStockTakes.filter { it.stockTakeType == "daily" }
            "monthly" -> allStockTakes.filter { it.stockTakeType == "monthly" }
            "draft" -> allStockTakes.filter { it.status == "draft" }
            "completed" -> allStockTakes.filter { it.status == "completed" }
            else -> allStockTakes.filter { it.status != "cancelled" }
        }
    }

    private fun renderHistory() {
        binding.historyList.removeAllViews()
        val items = filteredHistory()
        if (items.isEmpty()) {
            binding.historyList.addView(mutedText(getString(R.string.stock_take_empty_history)))
            return
        }
        items.forEach { stockTake ->
            val card = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(4, 10, 4, 10)
            }
            card.addView(TextView(this).apply {
                text = getString(
                    R.string.stock_take_history_meta,
                    stockTake.id,
                    stockTake.stockTakeTypeDisplay,
                    stockTake.countDate,
                    stockTake.lineCount.takeIf { it > 0 } ?: stockTake.lines.size,
                    stockTake.statusDisplay.ifBlank { stockTake.status },
                )
                setTextColor(getColor(R.color.text_primary))
                setTypeface(typeface, android.graphics.Typeface.BOLD)
            })
            card.addView(TextView(this).apply {
                val variances = if (stockTake.status == "completed") {
                    stockTake.varianceCount.toString()
                } else {
                    "—"
                }
                text = "${formatDate(stockTake.createdAt)} · variances $variances"
                setTextColor(getColor(R.color.text_muted))
                textSize = 13f
            })
            when (stockTake.status) {
                "draft" -> card.addView(actionButton(getString(R.string.stock_take_continue)) {
                    openStockTake(stockTake.id)
                })
                "completed" -> card.addView(
                    actionButton(getString(R.string.stock_take_view_details)) {
                        openStockTake(stockTake.id)
                    },
                )
            }
            binding.historyList.addView(card)
            binding.historyList.addView(divider())
        }
    }

    private fun renderActiveCount() {
        val stockTake = activeStockTake
        if (stockTake == null) {
            binding.activeCountCard.visibility = View.GONE
            lineInputs.clear()
            return
        }

        binding.activeCountCard.visibility = View.VISIBLE
        val isCompleted = stockTake.status == "completed"
        val lines = stockTake.lines
        val varianceLines = lines.filter { lineVariance(it) != null && lineVariance(it) != 0.0 }

        binding.activeCountTitle.text = if (isCompleted) {
            getString(
                R.string.stock_take_active_completed_title,
                stockTake.stockTakeTypeDisplay.lowercase(Locale.getDefault()),
                stockTake.id,
            )
        } else {
            getString(
                R.string.stock_take_active_title,
                stockTake.stockTakeTypeDisplay,
                stockTake.id,
            )
        }

        val branch = stockTake.branchName.ifBlank { session.branchName.orEmpty() }
        binding.activeCountMeta.text = if (isCompleted) {
            getString(
                R.string.stock_take_active_meta_variances,
                branch,
                stockTake.countDate,
                lines.size,
                varianceLines.size,
            )
        } else {
            getString(
                R.string.stock_take_active_meta,
                branch,
                stockTake.countDate,
                lines.size,
            )
        }

        binding.saveButton.visibility = if (isCompleted) View.GONE else View.VISIBLE
        binding.cancelCountButton.visibility = if (isCompleted) View.GONE else View.VISIBLE
        binding.completeButton.visibility = if (isCompleted) View.GONE else View.VISIBLE
        binding.closeCountButton.visibility = if (isCompleted) View.VISIBLE else View.GONE

        renderStationFilters(lines, isCompleted)
        renderLines(lines, isCompleted)
    }

    private fun stockTakeStationKey(line: StockTakeLine): String {
        return line.stockTakeStation.takeIf { it.isNotBlank() } ?: "shop"
    }

    private fun stockTakeStationLabel(line: StockTakeLine): String {
        return line.stockTakeStationDisplay.takeIf { it.isNotBlank() } ?: "Shop"
    }

    private fun renderStationFilters(lines: List<StockTakeLine>, isCompleted: Boolean) {
        binding.lineFilterChips.removeAllViews()
        val stations = STOCK_TAKE_STATION_ORDER.mapNotNull { key ->
            val count = lines.count { stockTakeStationKey(it) == key }
            if (count == 0) null else Triple(key, STOCK_TAKE_STATION_LABELS.getValue(key), count)
        }

        if (stations.size <= 1 && !isCompleted) {
            binding.lineFilterChips.visibility = View.GONE
            return
        }
        binding.lineFilterChips.visibility = View.VISIBLE

        fun addChip(label: String, key: String, checked: Boolean) {
            binding.lineFilterChips.addView(
                Chip(this).apply {
                    text = label
                    isCheckable = true
                    isChecked = checked
                    setOnClickListener {
                        stationFilter = key
                        val currentLines = activeStockTake?.lines ?: lines
                        renderLines(currentLines, isCompleted)
                        renderStationFilters(currentLines, isCompleted)
                    }
                },
            )
        }

        addChip(
            "All stations (${lines.size})",
            "all",
            stationFilter == "all",
        )
        stations.forEach { (key, label, count) ->
            addChip("$label ($count)", key, stationFilter == key)
        }
    }

    private fun renderLines(lines: List<StockTakeLine>, isCompleted: Boolean) {
        // Preserve typed values before rebuild when filtering stations.
        syncVisibleDraftsIntoActive()
        binding.countLinesList.removeAllViews()
        lineInputs.clear()

        val visible = if (stationFilter == "all") {
            lines
        } else {
            lines.filter { stockTakeStationKey(it) == stationFilter }
        }

        if (visible.isEmpty()) {
            binding.countLinesList.addView(mutedText(getString(R.string.stock_take_no_lines)))
            return
        }

        val groups = STOCK_TAKE_STATION_ORDER.mapNotNull { key ->
            val groupLines = visible.filter { stockTakeStationKey(it) == key }
            if (groupLines.isEmpty()) null else key to groupLines
        }

        if (!isCompleted) {
            binding.countLinesList.addView(
                LinearLayout(this).apply {
                    orientation = LinearLayout.HORIZONTAL
                    setPadding(0, 0, 0, 8)
                    addView(headerCell(getString(R.string.stock_take_ingredient), 1.3f))
                    addView(headerCell(getString(R.string.stock_take_counted), 0.7f))
                    addView(headerCell(getString(R.string.stock_take_wastage), 0.7f))
                    addView(headerCell(getString(R.string.stock_take_notes), 1.0f))
                },
            )
        } else {
            binding.countLinesList.addView(
                LinearLayout(this).apply {
                    orientation = LinearLayout.HORIZONTAL
                    setPadding(0, 0, 0, 8)
                    addView(headerCell(getString(R.string.stock_take_ingredient), 1.3f))
                    addView(headerCell(getString(R.string.stock_take_system_before), 0.65f))
                    addView(headerCell(getString(R.string.stock_take_counted), 0.65f))
                    addView(headerCell(getString(R.string.stock_take_wastage), 0.65f))
                    addView(headerCell(getString(R.string.stock_take_variance), 0.65f))
                },
            )
        }

        groups.forEach { (stationKey, groupLines) ->
            val stationLabel = STOCK_TAKE_STATION_LABELS[stationKey] ?: stockTakeStationLabel(groupLines.first())
            binding.countLinesList.addView(TextView(this).apply {
                text = getString(R.string.stock_take_station_header, stationLabel, groupLines.size)
                setTextColor(getColor(R.color.text_primary))
                setTypeface(typeface, android.graphics.Typeface.BOLD)
                setBackgroundColor(getColor(R.color.category_header_bg))
                setPadding(8, 10, 8, 10)
            })

            groupLines.forEach { line ->
                if (isCompleted) {
                    binding.countLinesList.addView(completedLineRow(line))
                } else {
                    binding.countLinesList.addView(draftLineRow(line))
                }
            }
        }
    }

    private fun draftLineRow(line: StockTakeLine): View {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = android.view.Gravity.CENTER_VERTICAL
            setPadding(4, 6, 4, 6)
        }
        row.addView(TextView(this).apply {
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1.3f)
            text = line.productName
            setTextColor(getColor(R.color.text_primary))
        })
        val counted = EditText(this).apply {
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 0.7f)
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
            hint = "0"
            setText(line.countedQuantity.orEmpty())
        }
        val wastageRaw = line.wastageQuantity.orEmpty().trim()
        val wastageDisplay = if (wastageRaw.isBlank() || wastageRaw.toDoubleOrNull() == 0.0) {
            ""
        } else {
            wastageRaw
        }
        val wastage = EditText(this).apply {
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 0.7f)
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
            hint = "0"
            setText(wastageDisplay)
        }
        val notes = EditText(this).apply {
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1.0f)
            inputType = InputType.TYPE_CLASS_TEXT
            hint = getString(R.string.stock_take_notes_hint)
            setText(line.notes)
        }
        row.addView(counted)
        row.addView(wastage)
        row.addView(notes)
        lineInputs[line.id] = LineInputs(line.id, counted, wastage, notes)
        return row
    }

    private fun completedLineRow(line: StockTakeLine): View {
        val variance = lineVariance(line)
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = android.view.Gravity.CENTER_VERTICAL
            setPadding(4, 8, 4, 8)
        }
        row.addView(TextView(this).apply {
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1.3f)
            text = line.productName
            setTextColor(getColor(R.color.text_primary))
        })
        row.addView(TextView(this).apply {
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 0.65f)
            text = formatQty(line.systemQuantity)
            gravity = android.view.Gravity.END
            setTextColor(getColor(R.color.text_primary))
        })
        row.addView(TextView(this).apply {
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 0.65f)
            text = formatQty(line.countedQuantity)
            gravity = android.view.Gravity.END
            setTextColor(getColor(R.color.text_primary))
        })
        row.addView(TextView(this).apply {
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 0.65f)
            text = formatQty(line.wastageQuantity)
            gravity = android.view.Gravity.END
            setTextColor(getColor(R.color.text_primary))
        })
        row.addView(TextView(this).apply {
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 0.65f)
            text = formatVariance(variance)
            gravity = android.view.Gravity.END
            setTextColor(
                when {
                    variance == null || variance == 0.0 -> getColor(R.color.text_muted)
                    variance > 0 -> getColor(R.color.status_ready)
                    else -> getColor(R.color.error)
                },
            )
        })
        return row
    }

    private fun syncVisibleDraftsIntoActive() {
        val stockTake = activeStockTake ?: return
        if (stockTake.status != "draft" || lineInputs.isEmpty()) return
        val updatedLines = stockTake.lines.map { line ->
            val input = lineInputs[line.id] ?: return@map line
            val raw = input.counted.text?.toString()?.trim().orEmpty()
            val wastageRaw = input.wastage.text?.toString()?.trim().orEmpty()
            line.copy(
                countedQuantity = raw.ifBlank { null },
                wastageQuantity = wastageRaw.ifBlank { "0" },
                notes = input.notes.text?.toString()?.trim().orEmpty(),
            )
        }
        activeStockTake = stockTake.copy(lines = updatedLines)
    }

    private fun collectLineUpdates(): List<StockTakeLineUpdate> {
        syncVisibleDraftsIntoActive()
        val stockTake = activeStockTake ?: return emptyList()
        return stockTake.lines.map { line ->
            val input = lineInputs[line.id]
            if (input != null) {
                val raw = input.counted.text?.toString()?.trim().orEmpty()
                val wastageRaw = input.wastage.text?.toString()?.trim().orEmpty()
                StockTakeLineUpdate(
                    id = line.id,
                    countedQuantity = raw.ifBlank { null },
                    wastageQuantity = wastageRaw.ifBlank { "0" },
                    notes = input.notes.text?.toString()?.trim().orEmpty(),
                )
            } else {
                StockTakeLineUpdate(
                    id = line.id,
                    countedQuantity = line.countedQuantity,
                    wastageQuantity = line.wastageQuantity ?: "0",
                    notes = line.notes,
                )
            }
        }
    }

    private fun saveProgress(complete: Boolean) {
        val stockTake = activeStockTake ?: run {
            Toast.makeText(this, R.string.stock_take_start_hint, Toast.LENGTH_SHORT).show()
            return
        }
        lifecycleScope.launch {
            showLoading(true)
            try {
                val updates = collectLineUpdates()
                val updated = withContext(Dispatchers.IO) {
                    api.updateStockTakeLines(stockTake.id, updates)
                }
                if (complete) {
                    withContext(Dispatchers.IO) { api.completeStockTake(stockTake.id) }
                    Toast.makeText(
                        this@StockTakeActivity,
                        R.string.stock_take_completed,
                        Toast.LENGTH_SHORT,
                    ).show()
                    allStockTakes = withContext(Dispatchers.IO) { api.fetchStockTakes() }
                    renderHistory()
                    openStockTake(stockTake.id)
                } else {
                    activeStockTake = updated
                    Toast.makeText(
                        this@StockTakeActivity,
                        R.string.stock_take_saved,
                        Toast.LENGTH_SHORT,
                    ).show()
                    allStockTakes = withContext(Dispatchers.IO) { api.fetchStockTakes() }
                    renderHistory()
                    renderActiveCount()
                }
            } catch (err: ApiException) {
                handleApiError(err)
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message.orEmpty()))
            } finally {
                showLoading(false)
            }
        }
    }

    private fun confirmComplete() {
        if (activeStockTake == null) {
            Toast.makeText(this, R.string.stock_take_start_hint, Toast.LENGTH_SHORT).show()
            return
        }
        MaterialAlertDialogBuilder(this)
            .setMessage(R.string.stock_take_complete_confirm)
            .setNegativeButton(android.R.string.cancel, null)
            .setPositiveButton(R.string.stock_take_complete) { _, _ ->
                saveProgress(complete = true)
            }
            .show()
    }

    private fun confirmCancel() {
        val stockTake = activeStockTake ?: return
        MaterialAlertDialogBuilder(this)
            .setMessage(R.string.stock_take_cancel_confirm)
            .setNegativeButton(android.R.string.cancel, null)
            .setPositiveButton(R.string.stock_take_cancel) { _, _ ->
                cancelCount(stockTake.id)
            }
            .show()
    }

    private fun cancelCount(stockTakeId: Int) {
        lifecycleScope.launch {
            showLoading(true)
            try {
                withContext(Dispatchers.IO) { api.cancelStockTake(stockTakeId) }
                activeStockTake = null
                Toast.makeText(this@StockTakeActivity, R.string.stock_take_cancelled, Toast.LENGTH_SHORT).show()
                allStockTakes = withContext(Dispatchers.IO) { api.fetchStockTakes() }
                renderHistory()
                renderActiveCount()
            } catch (err: ApiException) {
                handleApiError(err)
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message.orEmpty()))
            } finally {
                showLoading(false)
            }
        }
    }

    private fun selectedDate(): String {
        return binding.countDateInput.text?.toString()?.trim().orEmpty().ifBlank { todayIso() }
    }

    private fun todayIso(): String {
        val formatter = SimpleDateFormat("yyyy-MM-dd", Locale.US)
        formatter.timeZone = TimeZone.getDefault()
        return formatter.format(Date())
    }

    private fun lineVariance(line: StockTakeLine): Double? {
        line.variance?.toDoubleOrNull()?.let { return it }
        val counted = line.countedQuantity?.toDoubleOrNull() ?: return null
        val system = line.systemQuantity?.toDoubleOrNull() ?: 0.0
        return counted - system
    }

    private fun formatQty(value: String?): String {
        val qty = value?.toDoubleOrNull() ?: return "—"
        return DecimalFormat("#,##0.##").format(qty)
    }

    private fun formatVariance(value: Double?): String {
        if (value == null) return "—"
        val formatted = DecimalFormat("#,##0.##").format(value)
        return if (value > 0) "+$formatted" else formatted
    }

    private fun formatDate(value: String): String = value.replace('T', ' ').take(16)

    private fun headerCell(label: String, weight: Float): TextView {
        return TextView(this).apply {
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, weight)
            text = label
            setTextColor(getColor(R.color.text_muted))
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            textSize = 12f
        }
    }

    private fun mutedText(message: String): TextView {
        return TextView(this).apply {
            text = message
            setTextColor(getColor(R.color.text_muted))
            setPadding(0, 16, 0, 16)
        }
    }

    private fun actionButton(label: String, onClick: () -> Unit): com.google.android.material.button.MaterialButton {
        return com.google.android.material.button.MaterialButton(
            this,
            null,
            com.google.android.material.R.attr.materialButtonOutlinedStyle,
        ).apply {
            text = label
            setOnClickListener { onClick() }
        }
    }

    private fun divider(): View {
        return View(this).apply {
            setBackgroundColor(getColor(R.color.background))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                2,
            )
        }
    }

    private fun showLoading(show: Boolean) {
        binding.progress.visibility = if (show) View.VISIBLE else View.GONE
        binding.refreshButton.isEnabled = !show
        binding.startDailyButton.isEnabled = !show
        binding.startMonthlyButton.isEnabled = !show
        binding.saveButton.isEnabled = !show
        binding.completeButton.isEnabled = !show
        binding.cancelCountButton.isEnabled = !show
    }

    private fun handleApiError(err: ApiException) {
        if (err.statusCode == 401) {
            Toast.makeText(this, R.string.session_expired, Toast.LENGTH_LONG).show()
            logout()
        } else {
            showError(err.message ?: getString(R.string.stock_take_load_failed))
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
        private const val ERROR_BANNER_MS = 6_000L
        private val STOCK_TAKE_STATION_ORDER = listOf("kitchen", "bar", "shop")
        private val STOCK_TAKE_STATION_LABELS = mapOf(
            "kitchen" to "Kitchen",
            "bar" to "Bar",
            "shop" to "Shop",
        )
    }
}
