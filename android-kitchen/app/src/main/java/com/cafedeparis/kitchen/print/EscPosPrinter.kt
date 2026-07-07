package com.cafedeparis.kitchen.print

import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothSocket
import com.cafedeparis.kitchen.data.DayEndReportResponse
import com.cafedeparis.kitchen.data.KitchenOrder
import com.cafedeparis.kitchen.data.OrderItem
import com.cafedeparis.kitchen.data.OrderSlipPrintOptions
import org.json.JSONArray
import java.io.OutputStream
import java.nio.charset.Charset
import java.text.NumberFormat
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone
import java.util.UUID

class EscPosPrinter {

  fun printOrder(deviceAddress: String, order: KitchenOrder) {
    print(deviceAddress) { output ->
      writeKitchenTicket(output, order)
    }
  }

  fun printOrderSlip(
    deviceAddress: String,
    order: KitchenOrder,
    options: OrderSlipPrintOptions = OrderSlipPrintOptions(),
  ) {
    print(deviceAddress) { output ->
      writeOrderSlip(output, order, options)
    }
  }

  fun printReceipt(deviceAddress: String, order: KitchenOrder) {
    print(deviceAddress) { output ->
      writeSalesReceipt(output, order)
    }
  }

  fun printDayEnd(deviceAddress: String, payload: DayEndReportResponse) {
    print(deviceAddress) { output ->
      writeDayEndReport(output, payload)
    }
  }

  private fun print(deviceAddress: String, writer: (OutputStream) -> Unit) {
    val adapter = BluetoothAdapter.getDefaultAdapter()
      ?: throw PrinterException("Bluetooth is not available on this device")
    if (!adapter.isEnabled) {
      throw PrinterException("Bluetooth is turned off")
    }

    val device = adapter.getRemoteDevice(deviceAddress)
    val socket = createSocket(device)
    socket.connect()
    try {
      val output = socket.outputStream
      writer(output)
      output.flush()
      feedAndCut(output)
    } finally {
      runCatching { socket.close() }
    }
  }

  private fun createSocket(device: BluetoothDevice): BluetoothSocket {
    return try {
      device.createRfcommSocketToServiceRecord(SPP_UUID)
    } catch (_: Exception) {
      val method = device.javaClass.getMethod("createRfcommSocket", Int::class.javaPrimitiveType)
      method.invoke(device, 1) as BluetoothSocket
    }
  }

  private fun writeKitchenTicket(output: OutputStream, order: KitchenOrder) {
    output.write(INIT)
    output.write(ALIGN_CENTER)
    if (order.branch_fiscalization_enabled) {
      output.write(textLine("Cafe de Paris", doubleHeight = true))
      if (order.branch_name.isNotBlank()) {
        output.write(textLine(order.branch_name))
      }
      output.write(LF)
    }

    output.write(textLine("ORDER TICKET", bold = true))
    output.write(textLine("Order #${order.id}", bold = true))
    output.write(textLine(formatDateTime(order.created_at)))
    output.write(textLine(formatOrderType(order)))
    order.customer_name?.takeIf { it.isNotBlank() }?.let {
      output.write(textLine("Customer: $it"))
    }
    order.created_by_name?.takeIf { it.isNotBlank() }?.let {
      output.write(textLine("Served by $it"))
    }

    output.write(textLine("--------------------------------"))
    output.write(ALIGN_LEFT)

    for (item in order.items) {
      val qty = formatQty(item.quantity)
      output.write(textLine("$qty x ${item.product_name}", bold = true, large = true))
      for (addon in item.addons) {
        output.write(textLine("  + ${addon.name}"))
      }
      if (item.notes.isNotBlank()) {
        output.write(textLine("  Note: ${item.notes}"))
      }
    }

    output.write(textLine("--------------------------------"))
    output.write(LF)
    output.write(LF)
  }

  private fun writeOrderSlip(
    output: OutputStream,
    order: KitchenOrder,
    options: OrderSlipPrintOptions,
  ) {
    val tax = orderSlipTaxBreakdown(order, options.taxRate)
    val baseLabel = options.baseCurrencyCode?.let { " ($it)" }.orEmpty()

    output.write(INIT)
    output.write(ALIGN_CENTER)
    if (order.branch_fiscalization_enabled) {
      output.write(textLine("Cafe de Paris", doubleHeight = true))
      if (order.branch_name.isNotBlank()) {
        output.write(textLine(order.branch_name))
      }
      output.write(LF)
    }

    output.write(textLine("Order ticket", bold = true))
    output.write(textLine("Order #${order.id}"))
    output.write(textLine(formatDateTime(order.created_at)))
    output.write(textLine(formatOrderType(order)))
    order.customer_name?.takeIf { it.isNotBlank() }?.let {
      output.write(textLine("Customer: $it"))
    }
    order.created_by_name?.takeIf { it.isNotBlank() }?.let {
      output.write(textLine("Served by $it"))
    }

    output.write(textLine("--------------------------------"))
    output.write(ALIGN_LEFT)
    output.write(
      textLine(
        "Item".padEnd(ITEM_NAME_W) + "Qty".padStart(ITEM_QTY_W) + "Amt".padStart(ITEM_AMT_W),
        bold = true,
      ),
    )
    output.write(textLine("-".repeat(LINE_WIDTH)))

    if (order.items.isEmpty()) {
      output.write(textLine("No items"))
    } else {
      for (item in order.items) {
        val lineTotal = orderItemLineTotal(item)
        output.write(
          textLine(
            itemColumns(item.product_name, item.quantity, lineTotal),
            bold = true,
          ),
        )
        for (addon in item.addons) {
          val addonPrice = addon.price.toDoubleOrNull() ?: 0.0
          val addonLabel = if (addonPrice > 0.0) {
            "+ ${addon.name} (${formatPlainAmount(addon.price)})"
          } else {
            "+ ${addon.name}"
          }
          output.write(textLine("  $addonLabel"))
        }
        if (item.notes.isNotBlank()) {
          output.write(textLine("  Note: ${item.notes}"))
        }
        val unitPrice = itemUnitPrice(item)
        output.write(textLine("  ${formatPlainAmount(unitPrice.toString())} each"))
      }
    }

    output.write(textLine("--------------------------------"))
    if (order.branch_fiscalization_enabled) {
      output.write(textLine("Subtotal$baseLabel", suffix = formatPlainAmount(tax.subtotal.toString())))
      output.write(
        textLine(
          "Tax (${formatTaxRate(options.taxRate)})",
          suffix = formatPlainAmount(tax.tax.toString()),
        ),
      )
    }
    output.write(
      textLine(
        "Total$baseLabel",
        bold = true,
        suffix = formatPlainAmount(tax.total.toString()),
      ),
    )

    output.write(LF)
    output.write(ALIGN_CENTER)
    output.write(textLine("Present this ticket when paying."))
    output.write(textLine("UNPAID", bold = true, doubleHeight = true))
    output.write(LF)
  }

  private fun writeSalesReceipt(output: OutputStream, order: KitchenOrder) {
    val isProforma = order.fiscal_approval_status == "pending"

    output.write(INIT)
    output.write(ALIGN_CENTER)
    if (order.branch_fiscalization_enabled) {
      output.write(textLine("Cafe de Paris", doubleHeight = true))
      if (order.branch_name.isNotBlank()) {
        output.write(textLine(order.branch_name))
      }
      output.write(LF)
    }

    if (isProforma) {
      output.write(textLine("PROFORMA", bold = true))
      output.write(textLine("Proforma Receipt", bold = true))
      output.write(textLine("Not a fiscal receipt"))
      order.receipt_number?.takeIf { it.isNotBlank() }?.let {
        output.write(textLine("Proforma #$it"))
      }
    } else {
      output.write(textLine("Sales Receipt", bold = true))
      order.receipt_number?.takeIf { it.isNotBlank() }?.let {
        output.write(textLine("Receipt #$it"))
      }
    }

    output.write(textLine("Order #${order.id}"))
    output.write(textLine(formatDateTime(order.created_at)))
    output.write(textLine(formatOrderType(order)))
    order.customer_name?.takeIf { it.isNotBlank() }?.let {
      output.write(textLine("Customer: $it"))
    }
    (order.paid_by_name ?: order.created_by_name)?.takeIf { it.isNotBlank() }?.let {
      output.write(textLine("Served by $it"))
    }

    output.write(textLine("--------------------------------"))
    output.write(ALIGN_LEFT)

    for (item in order.items) {
      val qty = formatQty(item.quantity)
      val unitPrice = item.price.toDoubleOrNull() ?: 0.0
      val addonUnitPrice = item.addons.sumOf { it.price.toDoubleOrNull() ?: 0.0 }
      val quantity = item.quantity.toDoubleOrNull() ?: 0.0
      val lineTotal = (unitPrice + addonUnitPrice) * quantity
      output.write(textLine(item.product_name, bold = true))
      for (addon in item.addons) {
        output.write(textLine("  + ${addon.name}"))
      }
      if (item.notes.isNotBlank()) {
        output.write(textLine("  Note: ${item.notes}"))
      }
      output.write(
        textLine(
          "$qty @ ${formatMoney(unitPrice + addonUnitPrice)}",
          suffix = formatMoney(lineTotal),
        ),
      )
    }

    output.write(textLine("--------------------------------"))
    output.write(
      textLine(
        "Total",
        bold = true,
        suffix = formatMoney(order.total_amount),
      ),
    )

    if (order.payment_method == "account") {
      output.write(textLine("Paid from customer account", bold = true))
      order.customer_name?.takeIf { it.isNotBlank() }?.let {
        output.write(textLine("Account: $it"))
      }
    } else {
      order.payment_currency_name?.takeIf { it.isNotBlank() }?.let { currencyName ->
        output.write(textLine("Paid in: $currencyName"))
      }
      order.amount_paid?.takeIf { it.isNotBlank() }?.let { amount ->
        val symbol = order.payment_currency_symbol.orEmpty()
        val formatted = if (symbol.isNotBlank()) "$symbol${formatPlainAmount(amount)}" else formatMoney(amount)
        output.write(textLine("Amount paid", bold = true, suffix = formatted))
      }
    }

    output.write(LF)
    output.write(ALIGN_CENTER)
    output.write(textLine("Thank you for your visit!"))
    if (isProforma) {
      output.write(textLine("PROFORMA - NOT FISCAL", bold = true))
    }
    output.write(textLine("PAID", bold = true, doubleHeight = true))
    output.write(LF)
  }

  private fun writeDayEndReport(output: OutputStream, payload: DayEndReportResponse) {
    val report = payload.report
    val baseLabel = payload.baseCurrencyCode?.let { " ($it)" }.orEmpty()

    output.write(INIT)
    output.write(ALIGN_CENTER)
    output.write(textLine("Cafe de Paris", doubleHeight = true))
    payload.branchLocation?.takeIf { it.isNotBlank() }?.let {
      output.write(textLine(it))
    }
    output.write(LF)
    output.write(textLine("Day End Report", bold = true))
    output.write(textLine(formatReportDate(report.optString("report_date", ""))))
    output.write(textLine(formatDateTime(payload.printedAt)))
    output.write(textLine(payload.branchName))
    output.write(textLine("--------------------------------"))
    output.write(ALIGN_LEFT)

    val orderCount = report.optInt("order_count", 0)
    output.write(textLine("Orders", suffix = orderCount.toString()))
    val orderTypes = report.optJSONArray("order_types") ?: JSONArray()
    for (i in 0 until orderTypes.length()) {
      val row = orderTypes.getJSONObject(i)
      output.write(
        textLine(
          row.optString("label", ""),
          suffix = row.optString("count", "0"),
        ),
      )
    }

    output.write(textLine("--------------------------------"))
    output.write(ALIGN_CENTER)
    output.write(textLine("Sales$baseLabel", bold = true))
    output.write(ALIGN_LEFT)

    if (orderCount > 0) {
      val tax = report.optJSONObject("tax_breakdown")
      output.write(
        textLine(
          "Subtotal$baseLabel",
          suffix = formatMoney(tax?.optString("subtotal", "0") ?: "0"),
        ),
      )
      output.write(
        textLine(
          "Tax (${tax?.optString("tax_rate", "0") ?: "0"}%)",
          suffix = formatMoney(tax?.optString("tax", "0") ?: "0"),
        ),
      )
      output.write(
        textLine(
          "Total$baseLabel",
          bold = true,
          suffix = formatMoney(tax?.optString("total", "0") ?: "0"),
        ),
      )
    } else {
      output.write(textLine("No sales recorded"))
    }

    val payments = report.optJSONArray("payments") ?: JSONArray()
    if (payments.length() > 0) {
      output.write(textLine("--------------------------------"))
      output.write(ALIGN_CENTER)
      output.write(textLine("Payments collected", bold = true))
      output.write(ALIGN_LEFT)
      for (i in 0 until payments.length()) {
        val payment = payments.getJSONObject(i)
        val code = payment.optString("payment_currency__code", "")
          .ifBlank { payment.optString("payment_currency__name", "") }
        val symbol = payment.optString("payment_currency__symbol", "")
        val amount = payment.optString("total_paid", "0")
        val count = payment.optInt("order_count", 0)
        val formatted = if (symbol.isNotBlank()) "$symbol${formatPlainAmount(amount)}" else formatMoney(amount)
        output.write(textLine(code, suffix = "$formatted ($count)"))
      }
    }

    val expenses = report.optJSONArray("expenses") ?: JSONArray()
    if (expenses.length() > 0) {
      output.write(textLine("--------------------------------"))
      output.write(ALIGN_CENTER)
      output.write(textLine("Expenses", bold = true))
      output.write(ALIGN_LEFT)
      for (i in 0 until expenses.length()) {
        val expense = expenses.getJSONObject(i)
        val label = expense.optString("description", "Expense")
        val symbol = expense.optString("currency__symbol", "")
        val amount = expense.optString("amount", "0")
        val formatted = if (symbol.isNotBlank()) "$symbol${formatPlainAmount(amount)}" else formatMoney(amount)
        output.write(textLine(label, suffix = formatted))
      }
    }

    val cashupRows = report.optJSONArray("cashup_rows") ?: JSONArray()
    if (cashupRows.length() > 0) {
      output.write(textLine("--------------------------------"))
      output.write(ALIGN_CENTER)
      output.write(textLine("Cash-up reconciliation", bold = true))
      output.write(ALIGN_LEFT)
      for (i in 0 until cashupRows.length()) {
        val row = cashupRows.getJSONObject(i)
        val code = row.optString("payment_currency__code", "")
          .ifBlank { row.optString("payment_currency__name", "") }
        val symbol = row.optString("payment_currency__symbol", "")
        fun money(value: String?): String {
          if (value.isNullOrBlank()) return "—"
          return if (symbol.isNotBlank()) "$symbol${formatPlainAmount(value)}" else formatMoney(value)
        }
        output.write(textLine("$code expected", suffix = money(row.optString("expected_total"))))
        val expensesTotal = row.optString("expenses_total", "")
        if (expensesTotal.isNotBlank() && expensesTotal != "0" && expensesTotal != "0.00") {
          output.write(textLine("Less expenses", suffix = money(expensesTotal)))
          output.write(textLine("Net expected", suffix = money(row.optString("net_expected_total"))))
        }
        val counted = row.optString("counted_total", null)
        val variance = row.optString("variance", null)
        output.write(textLine("Counted", suffix = money(counted)))
        output.write(textLine("Variance", suffix = money(variance)))
      }
      if (report.optBoolean("has_counted_entries", false)) {
        output.write(
          textLine(
            "Total variance",
            bold = true,
            suffix = formatMoney(report.optString("variance_total", "0")),
          ),
        )
      }
    }

    output.write(textLine("--------------------------------"))
    output.write(ALIGN_CENTER)
    output.write(textLine("Items sold", bold = true))
    output.write(ALIGN_LEFT)
    val products = report.optJSONArray("products") ?: JSONArray()
    if (products.length() == 0) {
      output.write(textLine("No items sold"))
    } else {
      for (i in 0 until products.length()) {
        val product = products.getJSONObject(i)
        output.write(textLine(product.optString("product__name", ""), bold = true))
        val qty = formatQty(product.optString("quantity", "0"))
        val revenue = formatMoney(product.optString("revenue", "0"))
        output.write(textLine("$qty @", suffix = revenue))
      }
    }

    output.write(LF)
    output.write(ALIGN_CENTER)
    output.write(textLine("End of day summary"))
    output.write(LF)
  }

  private fun formatReportDate(value: String): String {
    return try {
      val parser = SimpleDateFormat("yyyy-MM-dd", Locale.US)
      val formatter = SimpleDateFormat("d MMM yyyy", Locale.US)
      val date = parser.parse(value.substring(0, 10))
      formatter.format(date!!)
    } catch (_: Exception) {
      value
    }
  }

  private fun feedAndCut(output: OutputStream) {
    output.write(byteArrayOf(0x1B, 0x64, 0x03)) // feed 3 lines
    output.write(byteArrayOf(0x1D, 0x56, 0x00)) // partial cut
  }

  private fun textLine(
    text: String,
    bold: Boolean = false,
    doubleHeight: Boolean = false,
    large: Boolean = false,
    suffix: String? = null,
  ): ByteArray {
    val line = if (suffix.isNullOrBlank()) {
      text
    } else {
      padColumns(text, suffix, LINE_WIDTH)
    }
    val bytes = mutableListOf<ByteArray>()
    if (bold) bytes.add(BOLD_ON)
    when {
      large -> bytes.add(LARGE_TEXT_ON)
      doubleHeight -> bytes.add(DOUBLE_HEIGHT_ON)
    }
    bytes.add(line.toByteArray(PRINTER_CHARSET))
    bytes.add(LF)
    when {
      large -> bytes.add(LARGE_TEXT_OFF)
      doubleHeight -> bytes.add(DOUBLE_HEIGHT_OFF)
    }
    if (bold) bytes.add(BOLD_OFF)
    return bytes.fold(ByteArray(0)) { acc, part -> acc + part }
  }

  private fun padColumns(left: String, right: String, width: Int): String {
    val trimmedLeft = left.take(width - right.length - 1)
    val spaces = (width - trimmedLeft.length - right.length).coerceAtLeast(1)
    return trimmedLeft + " ".repeat(spaces) + right
  }

  private fun truncText(text: String, max: Int): String {
    return if (text.length > max) "${text.take(max - 1)}." else text
  }

  private fun itemColumns(name: String, quantity: String, amount: Double): String {
    val label = truncText(name, ITEM_NAME_W).padEnd(ITEM_NAME_W)
    val qty = formatQty(quantity).padStart(ITEM_QTY_W)
    val amt = formatPlainAmount(amount.toString()).padStart(ITEM_AMT_W)
    return "$label$qty$amt"
  }

  private fun itemUnitPrice(item: OrderItem): Double {
    val productPrice = item.price.toDoubleOrNull() ?: 0.0
    val addonUnitPrice = item.addons.sumOf { it.price.toDoubleOrNull() ?: 0.0 }
    return roundMoney(productPrice + addonUnitPrice)
  }

  private fun orderItemLineTotal(item: OrderItem): Double {
    val qty = item.quantity.toDoubleOrNull() ?: 0.0
    return roundMoney(qty * itemUnitPrice(item))
  }

  private fun receiptTotalFromOrder(order: KitchenOrder): Double {
    var total = 0.0
    for (item in order.items) {
      total += orderItemLineTotal(item)
    }
    return roundMoney(total)
  }

  private data class OrderSlipTaxBreakdown(
    val subtotal: Double,
    val tax: Double,
    val total: Double,
  )

  private fun orderSlipTaxBreakdown(order: KitchenOrder, taxRate: Double): OrderSlipTaxBreakdown {
    val total = receiptTotalFromOrder(order).let { computed ->
      if (computed > 0.0) computed else order.total_amount.toDoubleOrNull() ?: 0.0
    }
    val divisor = 1.0 + taxRate / 100.0
    val subtotal = roundMoney(total / divisor)
    val tax = roundMoney(total - subtotal)
    return OrderSlipTaxBreakdown(subtotal, tax, roundMoney(total))
  }

  private fun roundMoney(amount: Double): Double {
    return Math.round(amount * 100.0) / 100.0
  }

  private fun formatTaxRate(rate: Double): String {
    return String.format(Locale.US, "%.1f", rate)
  }

  private fun formatOrderType(order: KitchenOrder): String {
    val type = when (order.order_type) {
      "dine_in" -> "Dine In"
      else -> "Takeaway"
    }
    return if (order.table_number.isNotBlank()) {
      "$type · Table ${order.table_number}"
    } else {
      type
    }
  }

  private fun formatDateTime(iso: String): String {
    return try {
      val parser = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US).apply {
        timeZone = TimeZone.getTimeZone("UTC")
      }
      val formatter = SimpleDateFormat("d MMM yyyy, HH:mm", Locale.US)
      val date = parser.parse(iso.substring(0, 19))
      formatter.format(date!!)
    } catch (_: Exception) {
      iso
    }
  }

  private fun formatQty(value: String): String {
    return value.toDoubleOrNull()?.let { qty ->
      if (qty % 1.0 == 0.0) qty.toInt().toString() else String.format(Locale.US, "%.2f", qty)
    } ?: value
  }

  private fun formatMoney(value: String): String {
    val amount = value.toDoubleOrNull() ?: 0.0
    return formatMoney(amount)
  }

  private fun formatMoney(amount: Double): String {
    return NumberFormat.getCurrencyInstance(Locale.US).format(amount)
  }

  private fun formatPlainAmount(value: String): String {
    val amount = value.toDoubleOrNull() ?: 0.0
    return String.format(Locale.US, "%.2f", amount)
  }

  companion object {
    private const val LINE_WIDTH = 32
    private const val ITEM_NAME_W = 16
    private const val ITEM_QTY_W = 5
    private const val ITEM_AMT_W = 8

    private val SPP_UUID: UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
    private val PRINTER_CHARSET: Charset = Charset.forName("ISO-8859-1")

    private val INIT = byteArrayOf(0x1B, 0x40)
    private val LF = byteArrayOf(0x0A)
    private val ALIGN_LEFT = byteArrayOf(0x1B, 0x61, 0x00)
    private val ALIGN_CENTER = byteArrayOf(0x1B, 0x61, 0x01)
    private val BOLD_ON = byteArrayOf(0x1B, 0x45, 0x01)
    private val BOLD_OFF = byteArrayOf(0x1B, 0x45, 0x00)
    private val DOUBLE_HEIGHT_ON = byteArrayOf(0x1B, 0x21, 0x10)
    private val DOUBLE_HEIGHT_OFF = byteArrayOf(0x1B, 0x21, 0x00)
    private val LARGE_TEXT_ON = byteArrayOf(0x1B, 0x21, 0x30)
    private val LARGE_TEXT_OFF = byteArrayOf(0x1B, 0x21, 0x00)
  }
}

class PrinterException(message: String) : Exception(message)
