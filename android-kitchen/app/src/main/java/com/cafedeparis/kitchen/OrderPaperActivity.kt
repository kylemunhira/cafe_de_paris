package com.cafedeparis.kitchen

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.ArrayAdapter
import android.widget.CheckBox
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.lifecycle.lifecycleScope
import com.cafedeparis.kitchen.data.ApiClient
import com.cafedeparis.kitchen.data.ApiException
import com.cafedeparis.kitchen.data.AppConfig
import com.cafedeparis.kitchen.data.Branch
import com.cafedeparis.kitchen.data.OrderPaper
import com.cafedeparis.kitchen.data.Product
import com.cafedeparis.kitchen.data.SessionManager
import com.cafedeparis.kitchen.databinding.ActivityOrderPaperBinding
import com.google.android.material.button.MaterialButton
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Locale

class OrderPaperActivity : KeepScreenOnActivity() {

    private lateinit var binding: ActivityOrderPaperBinding
    private lateinit var session: SessionManager
    private lateinit var api: ApiClient

    private var bakeryBranches: List<Branch> = emptyList()
    private var bakeryProducts: List<Product> = emptyList()
    private var papers: List<OrderPaper> = emptyList()
    private val draftLines = mutableListOf<Pair<Product, String>>()
    private val selectedPaperIds = linkedSetOf<Int>()
    private var loading = false
    private var errorHideJob: Job? = null
    private var standaloneHome = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityOrderPaperBinding.inflate(layoutInflater)
        setContentView(binding.root)

        session = SessionManager(this)
        api = ApiClient(session, AppConfig(this))
        if (!session.isLoggedIn || !session.canAccessOrderPapers) {
            Toast.makeText(this, R.string.order_paper_access_denied, Toast.LENGTH_LONG).show()
            finish()
            return
        }

        standaloneHome = intent.getBooleanExtra(EXTRA_STANDALONE_HOME, false) ||
            (!session.canAccessPos && !session.canAccessBakery && session.canAccessOrderPapers)

        binding.branchLabel.text = getString(
            R.string.order_paper_branch_label,
            session.branchName.orEmpty(),
        )
        binding.staffLabel.text = session.displayName.orEmpty()
        binding.neededDateInput.setText(tomorrowIso())

        binding.backButton.visibility = if (standaloneHome) View.GONE else View.VISIBLE
        binding.backButton.setOnClickListener { finish() }
        binding.refreshButton.setOnClickListener { loadPage() }
        binding.settingsButton.setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }
        binding.logoutButton.setOnClickListener { logout() }

        if (session.canCreateOrderPapers) {
            binding.createCard.visibility = View.VISIBLE
            binding.addLineButton.setOnClickListener { addDraftLine() }
            binding.saveDraftButton.setOnClickListener { savePaper(submit = false) }
            binding.submitButton.setOnClickListener { savePaper(submit = true) }
        } else {
            binding.createCard.visibility = View.GONE
        }

        if (session.canManageBakeryOrderPapers) {
            binding.bakeryManagePanel.visibility = View.VISIBLE
            binding.createProductionButton.setOnClickListener { createProductionFromSelected() }
        } else {
            binding.bakeryManagePanel.visibility = View.GONE
        }

        loadPage()
    }

    override fun onDestroy() {
        errorHideJob?.cancel()
        super.onDestroy()
    }

    private fun loadPage() {
        if (loading) return
        loading = true
        showLoading(true)
        binding.errorBanner.visibility = View.GONE
        lifecycleScope.launch {
            try {
                if (session.canCreateOrderPapers) {
                    val bakeries = withContext(Dispatchers.IO) { api.fetchBakeryBranches() }
                    bakeryBranches = bakeries
                    populateBakerySpinner()
                    bakeryProducts = withContext(Dispatchers.IO) { api.fetchBakeryProducts() }
                    populateProductSpinner()
                }
                papers = withContext(Dispatchers.IO) { api.fetchOrderPapers() }
                    .filter { it.status != "cancelled" }
                selectedPaperIds.retainAll(papers.map { it.id }.toSet())
                renderPapers()
                if (session.canManageBakeryOrderPapers) {
                    val demand = withContext(Dispatchers.IO) {
                        api.fetchOrderPaperDemand(binding.neededDateInput.text?.toString())
                    }
                    renderDemand(demand.paperCount, demand.productTotals)
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

    private fun populateBakerySpinner() {
        val labels = bakeryBranches.map { it.name }
        binding.bakerySpinner.adapter = ArrayAdapter(
            this,
            android.R.layout.simple_spinner_item,
            labels,
        ).also {
            it.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        }
    }

    private fun populateProductSpinner() {
        val labels = bakeryProducts.map { it.name }
        binding.productSpinner.adapter = ArrayAdapter(
            this,
            android.R.layout.simple_spinner_item,
            labels,
        ).also {
            it.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        }
    }

    private fun addDraftLine() {
        val product = bakeryProducts.getOrNull(binding.productSpinner.selectedItemPosition)
        val qty = binding.quantityInput.text?.toString()?.trim().orEmpty()
        val qtyValue = qty.toDoubleOrNull()
        if (product == null || qtyValue == null || qtyValue <= 0.0) {
            Toast.makeText(this, R.string.order_paper_line_error, Toast.LENGTH_SHORT).show()
            return
        }
        val existing = draftLines.indexOfFirst { it.first.id == product.id }
        if (existing >= 0) {
            val current = draftLines[existing].second.toDoubleOrNull() ?: 0.0
            draftLines[existing] = product to formatQty(current + qtyValue)
        } else {
            draftLines.add(product to formatQty(qtyValue))
        }
        binding.quantityInput.setText("")
        renderDraftLines()
    }

    private fun renderDraftLines() {
        binding.draftLinesList.removeAllViews()
        if (draftLines.isEmpty()) {
            binding.draftLinesList.addView(
                TextView(this).apply {
                    text = getString(R.string.order_paper_no_lines)
                    setTextColor(getColor(R.color.text_muted))
                },
            )
            return
        }
        draftLines.forEachIndexed { index, (product, qty) ->
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                setPadding(0, 6, 0, 6)
            }
            row.addView(
                TextView(this).apply {
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                    text = "$qty × ${product.name}"
                    setTextColor(getColor(R.color.text_primary))
                },
            )
            row.addView(
                MaterialButton(this, null, com.google.android.material.R.attr.materialButtonOutlinedStyle).apply {
                    text = getString(R.string.remove)
                    setOnClickListener {
                        draftLines.removeAt(index)
                        renderDraftLines()
                    }
                },
            )
            binding.draftLinesList.addView(row)
        }
    }

    private fun savePaper(submit: Boolean) {
        if (draftLines.isEmpty()) {
            Toast.makeText(this, R.string.order_paper_no_lines, Toast.LENGTH_SHORT).show()
            return
        }
        val bakery = selectedBakery()
        val neededDate = binding.neededDateInput.text?.toString()?.trim().orEmpty()
            .ifBlank { tomorrowIso().also { binding.neededDateInput.setText(it) } }
        if (bakery == null) {
            Toast.makeText(this, R.string.order_paper_no_bakery, Toast.LENGTH_LONG).show()
            return
        }
        if (neededDate.isBlank()) {
            Toast.makeText(this, R.string.order_paper_need_date, Toast.LENGTH_SHORT).show()
            return
        }
        showLoading(true)
        lifecycleScope.launch {
            try {
                withContext(Dispatchers.IO) {
                    api.createOrderPaper(
                        requestingBranchId = session.branchId,
                        bakeryId = bakery.id,
                        neededDate = neededDate,
                        notes = binding.notesInput.text?.toString()?.trim().orEmpty(),
                        submit = submit,
                        lines = draftLines.map { it.first.id to it.second },
                    )
                }
                Toast.makeText(
                    this@OrderPaperActivity,
                    if (submit) R.string.order_paper_submitted else R.string.order_paper_draft_saved,
                    Toast.LENGTH_SHORT,
                ).show()
                draftLines.clear()
                binding.notesInput.setText("")
                renderDraftLines()
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

    private fun selectedBakery(): Branch? {
        if (bakeryBranches.isEmpty()) return null
        val index = binding.bakerySpinner.selectedItemPosition
        return bakeryBranches.getOrNull(index).takeIf { index >= 0 }
            ?: bakeryBranches.firstOrNull()
    }

    private fun renderDemand(paperCount: Int, totals: List<Pair<String, String>>) {
        if (totals.isEmpty()) {
            binding.demandSummary.text = getString(R.string.order_paper_no_demand)
            return
        }
        val lines = totals.joinToString("\n") { "${it.second} × ${it.first}" }
        binding.demandSummary.text = getString(R.string.order_paper_demand_summary, paperCount, lines)
    }

    private fun renderPapers() {
        binding.papersList.removeAllViews()
        if (papers.isEmpty()) {
            binding.papersList.addView(
                TextView(this).apply {
                    text = getString(R.string.order_paper_empty)
                    setTextColor(getColor(R.color.text_muted))
                },
            )
            return
        }

        papers.forEach { paper ->
            val card = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(0, 10, 0, 10)
            }
            val selectable = session.canManageBakeryOrderPapers &&
                (paper.status == "submitted" || (paper.status == "accepted" && paper.productionSheetId == null))

            if (selectable) {
                card.addView(
                    CheckBox(this).apply {
                        text = getString(
                            R.string.order_paper_list_title,
                            paper.id,
                            paper.requestingBranchName,
                            paper.statusDisplay,
                        )
                        isChecked = selectedPaperIds.contains(paper.id)
                        setOnCheckedChangeListener { _, checked ->
                            if (checked) selectedPaperIds.add(paper.id) else selectedPaperIds.remove(paper.id)
                        }
                    },
                )
            } else {
                card.addView(
                    TextView(this).apply {
                        text = getString(
                            R.string.order_paper_list_title,
                            paper.id,
                            paper.requestingBranchName,
                            paper.statusDisplay,
                        )
                        setTextColor(getColor(R.color.text_primary))
                        textSize = 15f
                        setTypeface(typeface, android.graphics.Typeface.BOLD)
                    },
                )
            }

            val preview = paper.lines.take(4).joinToString("\n") {
                "${it.effectiveQuantity} × ${it.productName}"
            }
            card.addView(
                TextView(this).apply {
                    text = getString(
                        R.string.order_paper_list_meta,
                        paper.neededDate,
                        paper.lineCount,
                        paper.totalUnits,
                    ) + if (preview.isNotBlank()) "\n$preview" else ""
                    setTextColor(getColor(R.color.text_muted))
                },
            )

            val actions = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
            }
            if (session.canCreateOrderPapers && paper.status == "draft") {
                actions.addView(actionButton(R.string.order_paper_submit) {
                    runPaperAction { api.submitOrderPaper(paper.id) }
                })
            }
            if (
                (session.canCreateOrderPapers && paper.status in listOf("draft", "submitted")) ||
                (session.canManageBakeryOrderPapers && paper.status == "submitted")
            ) {
                actions.addView(actionButton(R.string.cancel) {
                    confirmCancel(paper)
                })
            }
            if (session.canManageBakeryOrderPapers && paper.status == "submitted") {
                actions.addView(actionButton(R.string.order_paper_accept) {
                    runPaperAction { api.acceptOrderPaper(paper.id) }
                })
            }
            if (actions.childCount > 0) {
                card.addView(actions)
            }
            binding.papersList.addView(card)
        }
    }

    private fun actionButton(labelRes: Int, onClick: () -> Unit): MaterialButton {
        return MaterialButton(this, null, com.google.android.material.R.attr.materialButtonOutlinedStyle).apply {
            text = getString(labelRes)
            setOnClickListener { onClick() }
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT,
            ).also { it.marginEnd = 8 }
        }
    }

    private fun confirmCancel(paper: OrderPaper) {
        AlertDialog.Builder(this)
            .setTitle(R.string.order_paper_cancel_title)
            .setMessage(getString(R.string.order_paper_cancel_confirm, paper.id))
            .setNegativeButton(R.string.cancel, null)
            .setPositiveButton(R.string.order_paper_cancel_title) { _, _ ->
                runPaperAction { api.cancelOrderPaper(paper.id) }
            }
            .show()
    }

    private fun runPaperAction(block: () -> OrderPaper) {
        showLoading(true)
        lifecycleScope.launch {
            try {
                withContext(Dispatchers.IO) { block() }
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

    private fun createProductionFromSelected() {
        if (selectedPaperIds.isEmpty()) {
            Toast.makeText(this, R.string.order_paper_select_papers, Toast.LENGTH_SHORT).show()
            return
        }
        val bakeryId = bakeryBranches.firstOrNull()?.id
            ?: papers.firstOrNull()?.bakeryId
            ?: session.branchId
        val date = binding.neededDateInput.text?.toString()?.trim().orEmpty().ifBlank { tomorrowIso() }
        showLoading(true)
        lifecycleScope.launch {
            try {
                val sheet = withContext(Dispatchers.IO) {
                    api.createProductionSheetFromOrderPapers(
                        bakeryId = bakeryId,
                        productionDate = date,
                        orderPaperIds = selectedPaperIds.toList(),
                    )
                }
                Toast.makeText(
                    this@OrderPaperActivity,
                    R.string.order_paper_production_created,
                    Toast.LENGTH_SHORT,
                ).show()
                startActivity(
                    Intent(this@OrderPaperActivity, BakeryProductionActivity::class.java).apply {
                        putExtra(BakeryProductionActivity.EXTRA_SHEET_ID, sheet.id)
                        addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP)
                    },
                )
                if (!standaloneHome) finish()
            } catch (err: ApiException) {
                handleApiError(err)
                showLoading(false)
            } catch (err: Exception) {
                showError(getString(R.string.connection_failed, err.message.orEmpty()))
                showLoading(false)
            }
        }
    }

    private fun showLoading(show: Boolean) {
        binding.progress.visibility = if (show) View.VISIBLE else View.GONE
    }

    private fun showError(message: String) {
        binding.errorBanner.text = message
        binding.errorBanner.visibility = View.VISIBLE
        errorHideJob?.cancel()
        errorHideJob = lifecycleScope.launch {
            delay(6_000)
            binding.errorBanner.visibility = View.GONE
        }
    }

    private fun handleApiError(err: ApiException) {
        if (err.statusCode == 401) {
            logout()
            return
        }
        showError(err.message ?: getString(R.string.connection_failed, ""))
    }

    private fun logout() {
        session.clearLogin()
        startActivity(
            Intent(this, MainActivity::class.java).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
            },
        )
        finish()
    }

    private fun tomorrowIso(): String {
        val cal = Calendar.getInstance()
        cal.add(Calendar.DAY_OF_YEAR, 1)
        return SimpleDateFormat("yyyy-MM-dd", Locale.US).format(cal.time)
    }

    private fun formatQty(value: Double): String {
        return if (value % 1.0 == 0.0) {
            value.toInt().toString()
        } else {
            String.format(Locale.US, "%.2f", value)
        }
    }

    companion object {
        const val EXTRA_STANDALONE_HOME = "standalone_home"
    }
}
