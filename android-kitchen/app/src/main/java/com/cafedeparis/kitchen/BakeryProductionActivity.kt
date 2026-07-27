package com.cafedeparis.kitchen

import android.content.Intent
import android.graphics.Typeface
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.core.widget.doAfterTextChanged
import androidx.lifecycle.lifecycleScope
import com.cafedeparis.kitchen.data.ApiClient
import com.cafedeparis.kitchen.data.ApiException
import com.cafedeparis.kitchen.data.AppConfig
import com.cafedeparis.kitchen.data.ProductionSheet
import com.cafedeparis.kitchen.data.SessionManager
import com.cafedeparis.kitchen.databinding.ActivityBakeryProductionBinding
import com.google.android.material.button.MaterialButton
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
    private var sheets: List<ProductionSheet> = emptyList()
    private var activeSheet: ProductionSheet? = null
    private val quantityInputs =
        linkedMapOf<Int, MutableMap<Int, EditText>>()
    private val totalViews = linkedMapOf<Int, TextView>()
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
        binding.productionDateInput.setText(todayIso())

        binding.transfersButton.setOnClickListener {
            startActivity(Intent(this, BakeryTransferActivity::class.java))
        }
        binding.refreshButton.setOnClickListener { loadPage() }
        binding.settingsButton.setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }
        binding.logoutButton.setOnClickListener { logout() }
        binding.startSheetButton.setOnClickListener { startSheet() }
        binding.saveSheetButton.setOnClickListener { saveSheet(complete = false) }
        binding.completeSheetButton.setOnClickListener { confirmComplete() }
        binding.cancelSheetButton.setOnClickListener { confirmCancel() }

        loadPage()
    }

    override fun onDestroy() {
        errorHideJob?.cancel()
        super.onDestroy()
    }

    override fun onResume() {
        super.onResume()
        if (::api.isInitialized) {
            loadPage()
        }
    }

    private fun loadPage(preferSheetId: Int? = null) {
        if (loading) return
        loading = true
        showLoading(true)
        binding.errorBanner.visibility = View.GONE
        lifecycleScope.launch {
            try {
                val list = withContext(Dispatchers.IO) { api.fetchProductionSheets() }
                sheets = list.filter { it.status != "cancelled" }
                renderStats()
                renderSheetsList()

                val openId = preferSheetId
                    ?: activeSheet?.id
                    ?: sheets.firstOrNull { it.status == "draft" }?.id
                if (openId != null) {
                    activeSheet = withContext(Dispatchers.IO) {
                        api.fetchProductionSheet(openId)
                    }
                    renderActiveSheet()
                    renderSheetsList()
                } else {
                    activeSheet = null
                    renderActiveSheet()
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

    private fun startSheet() {
        val date = binding.productionDateInput.text?.toString()?.trim().orEmpty()
            .ifBlank { todayIso() }
        showLoading(true)
        lifecycleScope.launch {
            try {
                val created = withContext(Dispatchers.IO) {
                    api.createProductionSheet(date)
                }
                Toast.makeText(
                    this@BakeryProductionActivity,
                    R.string.bakery_sheet_started,
                    Toast.LENGTH_SHORT,
                ).show()
                loadPage(preferSheetId = created.id)
            } catch (err: ApiException) {
                handleApiError(err)
                showLoading(false)
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message.orEmpty()))
                showLoading(false)
            }
        }
    }

    private fun openSheet(sheetId: Int, showLoadingSpinner: Boolean = true) {
        if (showLoadingSpinner) showLoading(true)
        lifecycleScope.launch {
            try {
                activeSheet = withContext(Dispatchers.IO) {
                    api.fetchProductionSheet(sheetId)
                }
                renderActiveSheet()
                renderSheetsList()
            } catch (err: ApiException) {
                handleApiError(err)
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message.orEmpty()))
            } finally {
                if (showLoadingSpinner) showLoading(false)
            }
        }
    }

    private fun renderStats() {
        val drafts = sheets.count { it.status == "draft" }
        val completed = sheets.count { it.status == "completed" }
        binding.draftStat.text = getString(R.string.bakery_draft_stat, drafts)
        binding.completedStat.text = getString(R.string.bakery_completed_stat, completed)
    }

    private fun renderSheetsList() {
        binding.sheetsList.removeAllViews()
        if (sheets.isEmpty()) {
            binding.sheetsList.addView(
                TextView(this).apply {
                    text = getString(R.string.bakery_no_sheets)
                    setTextColor(getColor(R.color.text_muted))
                    textSize = 13f
                },
            )
            return
        }

        sheets.forEach { sheet ->
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(0, 10, 0, 10)
            }
            row.addView(
                TextView(this).apply {
                    text = getString(
                        R.string.bakery_sheet_list_title,
                        sheet.id,
                        sheet.productionDate,
                        sheet.statusDisplay,
                    )
                    setTextColor(getColor(R.color.text_primary))
                    textSize = 14f
                    setTypeface(typeface, Typeface.BOLD)
                },
            )
            row.addView(
                TextView(this).apply {
                    text = getString(
                        R.string.bakery_sheet_list_meta,
                        sheet.lineCount,
                        sheet.producedLineCount,
                    )
                    setTextColor(getColor(R.color.text_muted))
                    textSize = 12f
                },
            )
            val openButton = MaterialButton(this).apply {
                text = if (sheet.status == "draft") {
                    getString(R.string.bakery_continue_sheet)
                } else {
                    getString(R.string.bakery_view_sheet)
                }
                setOnClickListener { openSheet(sheet.id) }
            }
            row.addView(openButton)
            binding.sheetsList.addView(row)
            binding.sheetsList.addView(
                View(this).apply { setBackgroundColor(getColor(R.color.background)) },
                LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 1),
            )
        }
    }

    private fun renderActiveSheet() {
        quantityInputs.clear()
        totalViews.clear()
        binding.sheetLines.removeAllViews()

        val sheet = activeSheet
        if (sheet == null) {
            binding.activeSheetTitle.text = getString(R.string.bakery_no_active_sheet)
            binding.activeSheetMeta.text = getString(R.string.bakery_start_or_open_sheet)
            setSheetActionsEnabled(draft = false, completed = false)
            return
        }

        val isDraft = sheet.status == "draft"
        val isCompleted = sheet.status == "completed"
        binding.activeSheetTitle.text = if (isCompleted) {
            getString(R.string.bakery_completed_sheet_title, sheet.id)
        } else {
            getString(R.string.bakery_active_sheet_title, sheet.id)
        }
        binding.activeSheetMeta.text = buildString {
            append(sheet.branchName)
            append(" · ")
            append(sheet.productionDate)
            append(" · ")
            append(getString(R.string.bakery_products_count, sheet.lines.size))
            if (isCompleted) {
                append(" · ")
                append(getString(R.string.bakery_produced_count, sheet.producedLineCount))
            }
        }
        setSheetActionsEnabled(draft = isDraft, completed = isCompleted)

        if (sheet.lines.isEmpty()) {
            binding.sheetLines.addView(
                TextView(this).apply {
                    text = getString(R.string.bakery_no_products)
                    setTextColor(getColor(R.color.text_muted))
                },
            )
            return
        }

        val destinations = sheet.destinations.ifEmpty {
            sheet.lines.firstOrNull()?.allocations?.map {
                com.cafedeparis.kitchen.data.ProductionDestination(
                    id = it.destinationBranchId,
                    name = it.destinationLabel,
                    label = it.destinationLabel,
                )
            }.orEmpty()
        }

        addHeaderRow(destinations.map { it.label })

        val groups = sheet.lines.groupBy { it.categoryName ?: getString(R.string.bakery_uncategorized) }
            .toSortedMap()
        groups.forEach { (category, lines) ->
            addCategoryHeader(category, lines.size)
            lines.forEach { line ->
                addProductRow(line, destinations, editable = isDraft)
            }
        }
    }

    private fun setSheetActionsEnabled(draft: Boolean, completed: Boolean) {
        binding.saveSheetButton.isEnabled = draft
        binding.completeSheetButton.isEnabled = draft
        binding.cancelSheetButton.isEnabled = draft
        binding.saveSheetButton.visibility = if (completed) View.GONE else View.VISIBLE
        binding.completeSheetButton.visibility = if (completed) View.GONE else View.VISIBLE
        binding.cancelSheetButton.visibility = if (completed) View.GONE else View.VISIBLE
    }

    private fun addHeaderRow(destinationLabels: List<String>) {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, 4, 0, 8)
        }
        row.addView(headerCell(getString(R.string.bakery_category), weight = 1.1f))
        row.addView(headerCell(getString(R.string.bakery_product_name), weight = 1.6f))
        destinationLabels.forEach { label ->
            row.addView(headerCell(label, weight = 1f, gravity = Gravity.END))
        }
        row.addView(headerCell(getString(R.string.bakery_total), weight = 0.8f, gravity = Gravity.END))
        binding.sheetLines.addView(row)
        binding.sheetLines.addView(divider())
    }

    private fun addCategoryHeader(name: String, count: Int) {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setBackgroundColor(getColor(R.color.category_header_bg))
            setPadding(8, 10, 8, 10)
        }
        row.addView(
            TextView(this).apply {
                text = getString(R.string.bakery_category_header, name.uppercase(Locale.US), count)
                setTextColor(getColor(R.color.text_primary))
                textSize = 13f
                setTypeface(typeface, Typeface.BOLD)
            },
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT,
            ),
        )
        binding.sheetLines.addView(row)
    }

    private fun addProductRow(
        line: com.cafedeparis.kitchen.data.ProductionSheetLine,
        destinations: List<com.cafedeparis.kitchen.data.ProductionDestination>,
        editable: Boolean,
    ) {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, 6, 0, 6)
        }
        row.addView(
            bodyCell(line.categoryName ?: "—", weight = 1.1f),
        )
        row.addView(
            bodyCell(line.productName, weight = 1.6f),
        )

        val lineInputs = linkedMapOf<Int, EditText>()
        destinations.forEach { destination ->
            val allocation = line.allocations.firstOrNull {
                it.destinationBranchId == destination.id
            }
            val quantity = allocation?.quantity.orEmpty()
            if (editable) {
                val input = EditText(this).apply {
                    inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
                    setText(quantity)
                    hint = "0"
                    setTextColor(getColor(R.color.text_primary))
                    textSize = 13f
                    gravity = Gravity.END
                    setPadding(8, 8, 8, 8)
                    background = getDrawable(android.R.drawable.edit_text)
                }
                input.doAfterTextChanged { updateRowTotal(line.id) }
                lineInputs[destination.id] = input
                row.addView(
                    input,
                    LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply {
                        marginEnd = 6
                    },
                )
            } else {
                row.addView(
                    bodyCell(formatQuantity(quantity.ifBlank { "0" }), weight = 1f, gravity = Gravity.END),
                )
            }
        }

        val totalView = TextView(this).apply {
            text = formatQuantity(lineTotal(line, destinations).toString())
            setTextColor(getColor(R.color.text_primary))
            textSize = 13f
            setTypeface(typeface, Typeface.BOLD)
            gravity = Gravity.END
        }
        row.addView(
            totalView,
            LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 0.8f),
        )

        if (editable) {
            quantityInputs[line.id] = lineInputs
            totalViews[line.id] = totalView
        }

        binding.sheetLines.addView(row)
        binding.sheetLines.addView(divider())
    }

    private fun lineTotal(
        line: com.cafedeparis.kitchen.data.ProductionSheetLine,
        destinations: List<com.cafedeparis.kitchen.data.ProductionDestination>,
    ): Double {
        return destinations.sumOf { destination ->
            line.allocations.firstOrNull { it.destinationBranchId == destination.id }
                ?.quantity
                ?.toDoubleOrNull()
                ?: 0.0
        }
    }

    private fun updateRowTotal(lineId: Int) {
        val inputs = quantityInputs[lineId] ?: return
        val total = inputs.values.sumOf {
            it.text?.toString()?.trim()?.toDoubleOrNull() ?: 0.0
        }
        totalViews[lineId]?.text = formatQuantity(total.toString())
    }

    private fun collectLineUpdates(): List<Pair<Int, List<Pair<Int, String?>>>> {
        val sheet = activeSheet ?: return emptyList()
        val destinations = sheet.destinations
        return sheet.lines.map { line ->
            val inputs = quantityInputs[line.id]
            val allocations = if (inputs != null) {
                destinations.map { destination ->
                    val raw = inputs[destination.id]?.text?.toString()?.trim().orEmpty()
                    destination.id to raw.ifBlank { null }
                }
            } else {
                line.allocations.map { allocation ->
                    allocation.destinationBranchId to allocation.quantity
                }
            }
            line.id to allocations
        }
    }

    private fun saveSheet(complete: Boolean) {
        val sheet = activeSheet ?: return
        if (sheet.status != "draft") return
        showLoading(true)
        lifecycleScope.launch {
            try {
                val updated = withContext(Dispatchers.IO) {
                    api.updateProductionSheetLines(sheet.id, collectLineUpdates())
                }
                if (complete) {
                    activeSheet = withContext(Dispatchers.IO) {
                        api.completeProductionSheet(sheet.id)
                    }
                    Toast.makeText(
                        this@BakeryProductionActivity,
                        R.string.bakery_sheet_completed,
                        Toast.LENGTH_LONG,
                    ).show()
                } else {
                    activeSheet = updated
                    Toast.makeText(
                        this@BakeryProductionActivity,
                        R.string.bakery_sheet_saved,
                        Toast.LENGTH_SHORT,
                    ).show()
                }
                sheets = withContext(Dispatchers.IO) { api.fetchProductionSheets() }
                    .filter { it.status != "cancelled" }
                renderStats()
                renderSheetsList()
                renderActiveSheet()
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
        AlertDialog.Builder(this)
            .setTitle(R.string.bakery_complete_production)
            .setMessage(R.string.bakery_complete_confirm)
            .setNegativeButton(android.R.string.cancel, null)
            .setPositiveButton(R.string.bakery_complete_production) { _, _ ->
                saveSheet(complete = true)
            }
            .show()
    }

    private fun confirmCancel() {
        val sheet = activeSheet ?: return
        AlertDialog.Builder(this)
            .setTitle(R.string.bakery_cancel_sheet)
            .setMessage(R.string.bakery_cancel_confirm)
            .setNegativeButton(android.R.string.cancel, null)
            .setPositiveButton(R.string.bakery_cancel_sheet) { _, _ ->
                showLoading(true)
                lifecycleScope.launch {
                    try {
                        withContext(Dispatchers.IO) { api.cancelProductionSheet(sheet.id) }
                        Toast.makeText(
                            this@BakeryProductionActivity,
                            R.string.bakery_sheet_cancelled,
                            Toast.LENGTH_SHORT,
                        ).show()
                        activeSheet = null
                        loadPage()
                    } catch (err: ApiException) {
                        handleApiError(err)
                        showLoading(false)
                    } catch (err: Exception) {
                        showError(getString(R.string.connection_failed, err.message.orEmpty()))
                        showLoading(false)
                    }
                }
            }
            .show()
    }

    private fun headerCell(
        text: String,
        weight: Float,
        gravity: Int = Gravity.START,
    ): TextView {
        return TextView(this).apply {
            this.text = text.uppercase(Locale.US)
            setTextColor(getColor(R.color.text_muted))
            textSize = 11f
            setTypeface(typeface, Typeface.BOLD)
            this.gravity = gravity
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, weight)
                .apply { marginEnd = 6 }
        }
    }

    private fun bodyCell(
        text: String,
        weight: Float,
        gravity: Int = Gravity.START,
    ): TextView {
        return TextView(this).apply {
            this.text = text
            setTextColor(getColor(R.color.text_primary))
            textSize = 13f
            this.gravity = gravity
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, weight)
                .apply { marginEnd = 6 }
        }
    }

    private fun divider(): View {
        return View(this).apply {
            setBackgroundColor(getColor(R.color.background))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                1,
            )
        }
    }

    private fun formatQuantity(value: String): String {
        return value.toDoubleOrNull()?.let { DecimalFormat("#,##0.##").format(it) } ?: value
    }

    private fun todayIso(): String {
        return SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date())
    }

    private fun showLoading(show: Boolean) {
        binding.progress.visibility = if (show) View.VISIBLE else View.GONE
        binding.refreshButton.isEnabled = !show
        binding.startSheetButton.isEnabled = !show
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

    companion object {
        private const val ERROR_BANNER_MS = 6_000L
    }
}
