package com.cafedeparis.kitchen.print

import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothSocket
import com.cafedeparis.kitchen.data.KitchenOrder
import java.io.OutputStream
import java.nio.charset.Charset
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone
import java.util.UUID

class EscPosPrinter {

  fun printOrder(deviceAddress: String, order: KitchenOrder) {
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
      writeTicket(output, order)
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

  private fun writeTicket(output: OutputStream, order: KitchenOrder) {
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
    }

    output.write(textLine("--------------------------------"))
    output.write(LF)
    output.write(LF)
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
  ): ByteArray {
    val bytes = mutableListOf<ByteArray>()
    if (bold) bytes.add(BOLD_ON)
    when {
      large -> bytes.add(LARGE_TEXT_ON)
      doubleHeight -> bytes.add(DOUBLE_HEIGHT_ON)
    }
    bytes.add(text.toByteArray(PRINTER_CHARSET))
    bytes.add(LF)
    when {
      large -> bytes.add(LARGE_TEXT_OFF)
      doubleHeight -> bytes.add(DOUBLE_HEIGHT_OFF)
    }
    if (bold) bytes.add(BOLD_OFF)
    return bytes.fold(ByteArray(0)) { acc, part -> acc + part }
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
    return value.toDoubleOrNull()?.let { String.format(Locale.US, "%.2f", it) } ?: value
  }

  companion object {
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
    private val LARGE_TEXT_ON = byteArrayOf(0x1B, 0x21, 0x30) // double height + double width
    private val LARGE_TEXT_OFF = byteArrayOf(0x1B, 0x21, 0x00)
  }
}

class PrinterException(message: String) : Exception(message)
