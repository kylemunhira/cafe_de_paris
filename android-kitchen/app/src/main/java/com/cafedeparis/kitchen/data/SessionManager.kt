package com.cafedeparis.kitchen.data

import android.content.Context

class SessionManager(context: Context) {
    private val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    var token: String?
        get() = prefs.getString(KEY_TOKEN, null)
        set(value) = prefs.edit().putString(KEY_TOKEN, value).apply()

    var branchId: Int
        get() = prefs.getInt(KEY_BRANCH_ID, -1)
        set(value) = prefs.edit().putInt(KEY_BRANCH_ID, value).apply()

    var branchName: String?
        get() = prefs.getString(KEY_BRANCH_NAME, null)
        set(value) = prefs.edit().putString(KEY_BRANCH_NAME, value).apply()

    var displayName: String?
        get() = prefs.getString(KEY_DISPLAY_NAME, null)
        set(value) = prefs.edit().putString(KEY_DISPLAY_NAME, value).apply()

    var userRole: String?
        get() = prefs.getString(KEY_USER_ROLE, null)
        set(value) = prefs.edit().putString(KEY_USER_ROLE, value).apply()

    var canCollectPayment: Boolean
        get() = prefs.getBoolean(KEY_CAN_COLLECT_PAYMENT, true)
        set(value) = prefs.edit().putBoolean(KEY_CAN_COLLECT_PAYMENT, value).apply()

    var isSuperuser: Boolean
        get() = prefs.getBoolean(KEY_IS_SUPERUSER, false)
        set(value) = prefs.edit().putBoolean(KEY_IS_SUPERUSER, value).apply()

    var kitchenStation: String?
        get() = prefs.getString(KEY_KITCHEN_STATION, null)
        set(value) = prefs.edit().putString(KEY_KITCHEN_STATION, value?.trim()).apply()

    var kitchenStationDisplay: String?
        get() = prefs.getString(KEY_KITCHEN_STATION_DISPLAY, null)
        set(value) = prefs.edit().putString(KEY_KITCHEN_STATION_DISPLAY, value?.trim()).apply()

    var canAccessKitchen: Boolean
        get() = prefs.getBoolean(KEY_CAN_ACCESS_KITCHEN, false)
        set(value) = prefs.edit().putBoolean(KEY_CAN_ACCESS_KITCHEN, value).apply()

    var canAccessPos: Boolean
        get() = prefs.getBoolean(KEY_CAN_ACCESS_POS, false)
        set(value) = prefs.edit().putBoolean(KEY_CAN_ACCESS_POS, value).apply()

    var canAccessBakery: Boolean
        get() = prefs.getBoolean(KEY_CAN_ACCESS_BAKERY, false)
        set(value) = prefs.edit().putBoolean(KEY_CAN_ACCESS_BAKERY, value).apply()

    var fiscalizationEnabled: Boolean
        get() = prefs.getBoolean(KEY_FISCALIZATION_ENABLED, false)
        set(value) = prefs.edit().putBoolean(KEY_FISCALIZATION_ENABLED, value).apply()

    var canManageFiscalDay: Boolean
        get() {
            if (prefs.contains(KEY_CAN_MANAGE_FISCAL_DAY)) {
                return prefs.getBoolean(KEY_CAN_MANAGE_FISCAL_DAY, false)
            }
            // Sessions saved before this flag: POS staff on fiscal branches (not waiters).
            return fiscalizationEnabled && canAccessPos && userRole != "waiter"
        }
        set(value) = prefs.edit().putBoolean(KEY_CAN_MANAGE_FISCAL_DAY, value).apply()

    var canApproveFiscalReceipt: Boolean
        get() {
            if (prefs.contains(KEY_CAN_APPROVE_FISCAL_RECEIPT)) {
                val stored = prefs.getBoolean(KEY_CAN_APPROVE_FISCAL_RECEIPT, false)
                // Older logins may have stored false for cashiers; fiscal POS staff can approve.
                return stored || canManageFiscalDay
            }
            return canManageFiscalDay
        }
        set(value) = prefs.edit().putBoolean(KEY_CAN_APPROVE_FISCAL_RECEIPT, value).apply()

    var canManageDiningTables: Boolean
        get() = prefs.getBoolean(KEY_CAN_MANAGE_DINING_TABLES, false)
        set(value) = prefs.edit().putBoolean(KEY_CAN_MANAGE_DINING_TABLES, value).apply()

    var printerAddress: String?
        get() = prefs.getString(KEY_PRINTER_ADDRESS, null)
        set(value) = prefs.edit().putString(KEY_PRINTER_ADDRESS, value?.trim()).apply()

    val isLoggedIn: Boolean
        get() = !token.isNullOrBlank() && branchId > 0

    fun shouldOpenPos(): Boolean {
        if (!canAccessPos) return false
        return when (userRole) {
            "cashier", "branch_manager", "waiter" -> true
            else -> canAccessPos && !canAccessKitchen
        }
    }

    /** Mobile GRV receiving is cashier-only (web GRV remains staff/management). */
    val canAccessGrv: Boolean
        get() = userRole == "cashier"

    fun saveLogin(response: LoginResponse) {
        token = response.token
        branchId = response.branch.id
        branchName = response.branch.name
        displayName = response.user.display_name
        userRole = response.user.role
        canAccessKitchen = response.can_access_kitchen
        canAccessPos = response.can_access_pos
        canAccessBakery = response.can_access_bakery
        canCollectPayment = response.user.can_collect_payment
        isSuperuser = response.user.is_superuser
        kitchenStation = response.user.kitchen_station
        kitchenStationDisplay = response.user.kitchen_station_display
        fiscalizationEnabled = response.branch.fiscalization_enabled
        canManageFiscalDay = response.user.can_manage_fiscal_day
        canApproveFiscalReceipt = response.user.can_approve_fiscal_receipt
        canManageDiningTables = response.user.can_manage_dining_tables
    }

    fun clearLogin() {
        prefs.edit()
            .remove(KEY_TOKEN)
            .remove(KEY_BRANCH_ID)
            .remove(KEY_BRANCH_NAME)
            .remove(KEY_DISPLAY_NAME)
            .remove(KEY_USER_ROLE)
            .remove(KEY_CAN_ACCESS_KITCHEN)
            .remove(KEY_CAN_ACCESS_POS)
            .remove(KEY_CAN_ACCESS_BAKERY)
            .remove(KEY_CAN_COLLECT_PAYMENT)
            .remove(KEY_IS_SUPERUSER)
            .remove(KEY_KITCHEN_STATION)
            .remove(KEY_KITCHEN_STATION_DISPLAY)
            .remove(KEY_FISCALIZATION_ENABLED)
            .remove(KEY_CAN_MANAGE_FISCAL_DAY)
            .remove(KEY_CAN_APPROVE_FISCAL_RECEIPT)
            .remove(KEY_CAN_MANAGE_DINING_TABLES)
            .apply()
    }

    fun markPrinted(orderId: Int, fingerprint: String = LEGACY_PRINT_FINGERPRINT) {
        val map = getPrintedOrderFingerprints().toMutableMap()
        map[orderId] = fingerprint
        // Keep the map from growing forever across long shifts.
        if (map.size > MAX_PRINTED_TRACKED) {
            val keep = map.entries.sortedByDescending { it.key }.take(MAX_PRINTED_TRACKED)
            map.clear()
            keep.forEach { map[it.key] = it.value }
        }
        prefs.edit()
            .putString(KEY_PRINTED_FINGERPRINTS, encodePrintedFingerprints(map))
            .remove(KEY_PRINTED_IDS)
            .apply()
    }

    fun getPrintedOrderIds(): Set<Int> = getPrintedOrderFingerprints().keys

    fun getPrintedOrderFingerprints(): Map<Int, String> {
        val encoded = prefs.getString(KEY_PRINTED_FINGERPRINTS, null)
        if (!encoded.isNullOrBlank()) {
            return decodePrintedFingerprints(encoded)
        }
        // Migrate legacy "printed once by id" set so we do not reprint every open ticket.
        val legacyIds = prefs.getStringSet(KEY_PRINTED_IDS, emptySet())
            ?.mapNotNull { it.toIntOrNull() }
            .orEmpty()
        if (legacyIds.isEmpty()) return emptyMap()
        return legacyIds.associateWith { LEGACY_PRINT_FINGERPRINT }
    }

    fun clearPrintedOrderIds() {
        prefs.edit()
            .remove(KEY_PRINTED_IDS)
            .remove(KEY_PRINTED_FINGERPRINTS)
            .apply()
    }

    var cancellationPollSince: String?
        get() = prefs.getString(KEY_CANCELLATION_POLL_SINCE, null)
        set(value) = prefs.edit().putString(KEY_CANCELLATION_POLL_SINCE, value).apply()

    fun ensureCancellationPollSince(nowIso: String) {
        if (cancellationPollSince.isNullOrBlank()) {
            cancellationPollSince = nowIso
        }
    }

    fun getPrintedCancelOrderIds(): Set<Int> {
        return prefs.getStringSet(KEY_PRINTED_CANCEL_IDS, emptySet())
            ?.mapNotNull { it.toIntOrNull() }
            ?.toSet()
            .orEmpty()
    }

    fun markCancelPrinted(orderId: Int) {
        val ids = getPrintedCancelOrderIds().toMutableSet()
        ids.add(orderId)
        if (ids.size > MAX_PRINTED_TRACKED) {
            val keep = ids.sortedDescending().take(MAX_PRINTED_TRACKED)
            ids.clear()
            ids.addAll(keep)
        }
        prefs.edit()
            .putStringSet(KEY_PRINTED_CANCEL_IDS, ids.map { it.toString() }.toSet())
            .apply()
    }

    fun clearCancellationTracking() {
        prefs.edit()
            .remove(KEY_CANCELLATION_POLL_SINCE)
            .remove(KEY_PRINTED_CANCEL_IDS)
            .remove(KEY_PRINTED_ITEM_SNAPSHOTS)
            .apply()
    }

    fun getPrintedItemSnapshot(orderId: Int): List<OrderItem> {
        return getAllPrintedItemSnapshots()[orderId].orEmpty()
    }

    fun setPrintedItemSnapshot(orderId: Int, items: List<OrderItem>) {
        val snapshots = getAllPrintedItemSnapshots().toMutableMap()
        if (items.isEmpty()) {
            snapshots.remove(orderId)
        } else {
            snapshots[orderId] = items
        }
        savePrintedItemSnapshots(snapshots)
    }

    fun removePrintedItemSnapshot(orderId: Int) {
        setPrintedItemSnapshot(orderId, emptyList())
    }

    private fun getAllPrintedItemSnapshots(): Map<Int, List<OrderItem>> {
        val encoded = prefs.getString(KEY_PRINTED_ITEM_SNAPSHOTS, null) ?: return emptyMap()
        if (encoded.isBlank()) return emptyMap()
        val snapshots = linkedMapOf<Int, List<OrderItem>>()
        for (part in encoded.split(ORDER_SNAPSHOT_SEP)) {
            if (part.isBlank()) continue
            val sep = part.indexOf('=')
            if (sep <= 0) continue
            val orderId = part.substring(0, sep).toIntOrNull() ?: continue
            val itemsJson = part.substring(sep + 1)
            snapshots[orderId] = decodeOrderItems(itemsJson)
        }
        return snapshots
    }

    private fun savePrintedItemSnapshots(snapshots: Map<Int, List<OrderItem>>) {
        if (snapshots.isEmpty()) {
            prefs.edit().remove(KEY_PRINTED_ITEM_SNAPSHOTS).apply()
            return
        }
        val trimmed = snapshots.entries
            .sortedByDescending { it.key }
            .take(MAX_PRINTED_TRACKED)
            .associate { it.key to it.value }
        val encoded = trimmed.entries.joinToString(ORDER_SNAPSHOT_SEP) { (orderId, items) ->
            "$orderId=${encodeOrderItems(items)}"
        }
        prefs.edit().putString(KEY_PRINTED_ITEM_SNAPSHOTS, encoded).apply()
    }

    private fun encodeOrderItems(items: List<OrderItem>): String {
        val array = org.json.JSONArray()
        for (item in items) {
            val addons = org.json.JSONArray()
            for (addon in item.addons) {
                addons.put(
                    org.json.JSONObject()
                        .put("name", addon.name)
                        .put("price", addon.price),
                )
            }
            array.put(
                org.json.JSONObject()
                    .put("id", item.id)
                    .put("product_name", item.product_name)
                    .put("quantity", item.quantity)
                    .put("price", item.price)
                    .put("notes", item.notes)
                    .put("addons", addons),
            )
        }
        return array.toString()
    }

    private fun decodeOrderItems(encoded: String): List<OrderItem> {
        return try {
            val array = org.json.JSONArray(encoded)
            (0 until array.length()).map { index ->
                val item = array.getJSONObject(index)
                val addonsJson = item.optJSONArray("addons") ?: org.json.JSONArray()
                val addons = (0 until addonsJson.length()).map { addonIndex ->
                    val addon = addonsJson.getJSONObject(addonIndex)
                    OrderItemAddon(
                        name = addon.optString("name", ""),
                        price = addon.optString("price", "0"),
                    )
                }
                OrderItem(
                    id = item.getInt("id"),
                    product_name = item.optString("product_name", ""),
                    quantity = item.optString("quantity", "0"),
                    price = item.optString("price", "0"),
                    notes = item.optString("notes", ""),
                    addons = addons,
                )
            }
        } catch (_: Exception) {
            emptyList()
        }
    }

    companion object {
        private const val PREFS_NAME = "kitchen_session"
        private const val KEY_TOKEN = "token"
        private const val KEY_BRANCH_ID = "branch_id"
        private const val KEY_BRANCH_NAME = "branch_name"
        private const val KEY_DISPLAY_NAME = "display_name"
        private const val KEY_USER_ROLE = "user_role"
        private const val KEY_CAN_ACCESS_KITCHEN = "can_access_kitchen"
        private const val KEY_CAN_ACCESS_POS = "can_access_pos"
        private const val KEY_CAN_ACCESS_BAKERY = "can_access_bakery"
        private const val KEY_CAN_COLLECT_PAYMENT = "can_collect_payment"
        private const val KEY_IS_SUPERUSER = "is_superuser"
        private const val KEY_KITCHEN_STATION = "kitchen_station"
        private const val KEY_KITCHEN_STATION_DISPLAY = "kitchen_station_display"
        private const val KEY_FISCALIZATION_ENABLED = "fiscalization_enabled"
        private const val KEY_CAN_MANAGE_FISCAL_DAY = "can_manage_fiscal_day"
        private const val KEY_CAN_APPROVE_FISCAL_RECEIPT = "can_approve_fiscal_receipt"
        private const val KEY_CAN_MANAGE_DINING_TABLES = "can_manage_dining_tables"
        private const val KEY_PRINTER_ADDRESS = "printer_address"
        private const val KEY_PRINTED_IDS = "printed_order_ids"
        private const val KEY_PRINTED_FINGERPRINTS = "printed_order_fingerprints"
        private const val KEY_CANCELLATION_POLL_SINCE = "cancellation_poll_since"
        private const val KEY_PRINTED_CANCEL_IDS = "printed_cancel_order_ids"
        private const val KEY_PRINTED_ITEM_SNAPSHOTS = "printed_item_snapshots"
        private const val ORDER_SNAPSHOT_SEP = "\u001e"
        const val LEGACY_PRINT_FINGERPRINT = "legacy"
        private const val MAX_PRINTED_TRACKED = 250

        fun orderPrintFingerprint(order: KitchenOrder): String {
            return order.items
                .map { "${it.id}:${it.quantity}" }
                .sorted()
                .joinToString("|")
        }

        private fun encodePrintedFingerprints(map: Map<Int, String>): String {
            return map.entries.joinToString(";") { "${it.key}=${it.value}" }
        }

        private fun decodePrintedFingerprints(encoded: String): Map<Int, String> {
            if (encoded.isBlank()) return emptyMap()
            return encoded.split(";")
                .mapNotNull { part ->
                    val sep = part.indexOf('=')
                    if (sep <= 0) return@mapNotNull null
                    val id = part.substring(0, sep).toIntOrNull() ?: return@mapNotNull null
                    id to part.substring(sep + 1)
                }
                .toMap()
        }
    }
}

object JsonParsers {
    fun parseLoginResponse(body: String): LoginResponse {
        val json = org.json.JSONObject(body)
        val user = json.getJSONObject("user")
        val branch = json.getJSONObject("branch")
        return LoginResponse(
            token = json.getString("token"),
            user = UserInfo(
                id = user.getInt("id"),
                username = user.getString("username"),
                display_name = user.getString("display_name"),
                role = user.getString("role"),
                can_manage_fiscal_day = user.optBoolean("can_manage_fiscal_day", false),
                can_approve_fiscal_receipt = user.optBoolean("can_approve_fiscal_receipt", false),
                can_manage_dining_tables = user.optBoolean("can_manage_dining_tables", false),
                can_collect_payment = user.optBoolean("can_collect_payment", true),
                is_superuser = user.optBoolean("is_superuser", false),
                kitchen_station = user.optString("kitchen_station", null)?.takeIf { it.isNotBlank() },
                kitchen_station_display = user.optString("kitchen_station_display", null)?.takeIf { it.isNotBlank() },
            ),
            branch = Branch(
                id = branch.getInt("id"),
                name = branch.getString("name"),
                location = branch.optString("location", null),
                fiscalization_enabled = branch.optBoolean("fiscalization_enabled", false),
                branch_type = branch.optString("branch_type", null),
                is_active = branch.optBoolean("is_active", true),
            ),
            can_access_kitchen = json.optBoolean("can_access_kitchen", false),
            can_access_pos = json.optBoolean("can_access_pos", false),
            can_access_bakery = json.optBoolean("can_access_bakery", false),
        )
    }

    fun parseOrders(body: String): List<KitchenOrder> {
        val json = org.json.JSONObject(body)
        val results = json.optJSONArray("results") ?: org.json.JSONArray()
        return (0 until results.length()).map { index ->
            parseOrder(results.getJSONObject(index))
        }
    }

    fun parseOrder(body: String): KitchenOrder = parseOrder(org.json.JSONObject(body))

    fun parseProducts(body: String): List<Product> {
        val json = org.json.JSONObject(body)
        val results = json.optJSONArray("results") ?: org.json.JSONArray()
        return (0 until results.length()).mapNotNull { index ->
            try {
                parseProduct(results.getJSONObject(index))
            } catch (_: Exception) {
                null
            }
        }
    }

    fun parseProductionPreview(body: String): ProductionPreview {
        val json = org.json.JSONObject(body)
        val linesJson = json.optJSONArray("lines") ?: org.json.JSONArray()
        val lines = (0 until linesJson.length()).map { index ->
            val line = linesJson.getJSONObject(index)
            ProductionPreviewLine(
                ingredientName = line.optString("ingredient_name", "Ingredient"),
                ingredientCategory = line.optString("ingredient_category", ""),
                required = jsonNumberAsString(line, "required", "0"),
                available = jsonNumberAsString(line, "available", "0"),
                sufficient = line.optBoolean("sufficient", false),
            )
        }
        return ProductionPreview(
            productName = json.optString("product_name", "Product"),
            quantity = jsonNumberAsString(json, "quantity", "0"),
            canProduce = json.optBoolean("can_produce", false),
            lines = lines,
        )
    }

    fun parseProductionOrders(body: String): List<ProductionOrder> {
        val json = org.json.JSONObject(body)
        val results = json.optJSONArray("results") ?: org.json.JSONArray()
        return (0 until results.length()).map { index ->
            val item = results.getJSONObject(index)
            ProductionOrder(
                id = item.getInt("id"),
                productName = item.optString("product_name", "Product"),
                quantity = jsonNumberAsString(item, "quantity", "0"),
                createdByName = item.optString("created_by_name", null)
                    ?.takeIf { it.isNotBlank() && it != "null" },
                createdAt = item.optString("created_at", ""),
            )
        }
    }

    fun parseProductionOrder(body: String): ProductionOrder {
        val item = org.json.JSONObject(body)
        return ProductionOrder(
            id = item.getInt("id"),
            productName = item.optString("product_name", "Product"),
            quantity = jsonNumberAsString(item, "quantity", "0"),
            createdByName = item.optString("created_by_name", null)
                ?.takeIf { it.isNotBlank() && it != "null" },
            createdAt = item.optString("created_at", ""),
        )
    }

    fun parseProductionSheets(body: String): List<ProductionSheet> {
        val json = org.json.JSONObject(body)
        val results = json.optJSONArray("results") ?: org.json.JSONArray()
        return (0 until results.length()).map { index ->
            parseProductionSheetObject(results.getJSONObject(index))
        }
    }

    fun parseProductionSheet(body: String): ProductionSheet {
        return parseProductionSheetObject(org.json.JSONObject(body))
    }

    private fun parseProductionSheetObject(json: org.json.JSONObject): ProductionSheet {
        val destinationsJson = json.optJSONArray("destinations") ?: org.json.JSONArray()
        val destinations = (0 until destinationsJson.length()).map { index ->
            val item = destinationsJson.getJSONObject(index)
            ProductionDestination(
                id = item.getInt("id"),
                name = item.optString("name", ""),
                label = item.optString("label", item.optString("name", "Qty")),
            )
        }
        val linesJson = json.optJSONArray("lines") ?: org.json.JSONArray()
        val lines = (0 until linesJson.length()).map { index ->
            val line = linesJson.getJSONObject(index)
            val allocationsJson = line.optJSONArray("allocations") ?: org.json.JSONArray()
            val allocations = (0 until allocationsJson.length()).map { allocIndex ->
                val allocation = allocationsJson.getJSONObject(allocIndex)
                val quantity = if (allocation.isNull("quantity")) {
                    null
                } else {
                    jsonNumberAsString(allocation, "quantity", "")
                        .takeIf { it.isNotBlank() }
                }
                ProductionSheetAllocation(
                    id = allocation.optInt("id", 0),
                    destinationBranchId = allocation.getInt("destination_branch"),
                    destinationLabel = allocation.optString(
                        "destination_label",
                        allocation.optString("destination_branch_name", "Qty"),
                    ),
                    quantity = quantity,
                )
            }
            ProductionSheetLine(
                id = line.getInt("id"),
                productId = line.getInt("product"),
                productName = line.optString("product_name", "Product"),
                categoryName = line.optString("category_name", null)
                    ?.takeIf { it.isNotBlank() && it != "null" },
                allocations = allocations,
                totalQuantity = jsonNumberAsString(line, "total_quantity", "0"),
            )
        }
        return ProductionSheet(
            id = json.getInt("id"),
            branchName = json.optString("branch_name", ""),
            productionDate = json.optString("production_date", ""),
            status = json.optString("status", "draft"),
            statusDisplay = json.optString(
                "status_display",
                json.optString("status", "Draft"),
            ),
            lineCount = json.optInt("line_count", lines.size),
            producedLineCount = json.optInt("produced_line_count", 0),
            completedAt = json.optString("completed_at", null)
                ?.takeIf { it.isNotBlank() && it != "null" },
            destinations = destinations,
            lines = lines,
        )
    }

    fun parseInventory(body: String): List<InventoryItem> {
        val json = org.json.JSONObject(body)
        val results = json.optJSONArray("results") ?: org.json.JSONArray()
        return (0 until results.length()).map { index ->
            val item = results.getJSONObject(index)
            InventoryItem(
                productId = item.getInt("product"),
                quantity = jsonNumberAsString(item, "quantity", "0"),
            )
        }
    }

    fun parseBranches(body: String): List<Branch> {
        val results = if (body.trimStart().startsWith("[")) {
            org.json.JSONArray(body)
        } else {
            org.json.JSONObject(body).optJSONArray("results") ?: org.json.JSONArray()
        }
        return (0 until results.length()).map { index ->
            val item = results.getJSONObject(index)
            Branch(
                id = item.getInt("id"),
                name = item.getString("name"),
                location = item.optString("location", null),
                fiscalization_enabled = item.optBoolean("fiscalization_enabled", false),
                branch_type = item.optString("branch_type", null),
                is_active = item.optBoolean("is_active", true),
            )
        }
    }

    fun parseDeliveryNotes(body: String): List<DeliveryNote> {
        val json = org.json.JSONObject(body)
        val results = json.optJSONArray("results") ?: org.json.JSONArray()
        return (0 until results.length()).map { index ->
            parseDeliveryNoteObject(results.getJSONObject(index))
        }
    }

    fun parseDeliveryNote(body: String): DeliveryNote {
        return parseDeliveryNoteObject(org.json.JSONObject(body))
    }

    private fun parseDeliveryNoteObject(item: org.json.JSONObject): DeliveryNote {
        val linesJson = item.optJSONArray("lines") ?: org.json.JSONArray()
        val lines = (0 until linesJson.length()).map { index ->
            val line = linesJson.getJSONObject(index)
            DeliveryNoteLine(
                id = line.getInt("id"),
                productId = line.getInt("product"),
                productName = line.optString("product_name", "Product"),
                quantity = jsonNumberAsString(line, "quantity", "0"),
                receivedQuantity = if (line.isNull("received_quantity")) {
                    null
                } else {
                    jsonNumberAsString(line, "received_quantity", "0")
                },
                damagedQuantity = jsonNumberAsString(line, "damaged_quantity", "0"),
                lineNotes = line.optString("line_notes", ""),
            )
        }
        return DeliveryNote(
            id = item.getInt("id"),
            sourceName = item.optString("from_branch_name", "Central Bakery"),
            sourceLocation = item.optString("from_branch_location", null)
                ?.takeIf { it.isNotBlank() && it != "null" },
            destinationName = item.optString("to_branch_name", "Destination"),
            destinationLocation = item.optString("to_branch_location", null)
                ?.takeIf { it.isNotBlank() && it != "null" },
            status = item.optString("status", "requested"),
            createdAt = item.optString("created_at", ""),
            totalQuantity = jsonNumberAsString(item, "total_quantity", "0"),
            remarks = item.optString("remarks", ""),
            isFlagged = item.optBoolean("is_flagged", false),
            lines = lines,
        )
    }

    private fun parseProduct(item: org.json.JSONObject): Product {
        val addonGroupsJson = item.optJSONArray("addon_groups") ?: org.json.JSONArray()
        val addonGroups = (0 until addonGroupsJson.length()).mapNotNull { groupIndex ->
            try {
                val group = addonGroupsJson.getJSONObject(groupIndex)
                val addonsJson = group.optJSONArray("addons") ?: org.json.JSONArray()
                val addons = (0 until addonsJson.length()).mapNotNull { addonIndex ->
                    try {
                        val addon = addonsJson.getJSONObject(addonIndex)
                        MenuAddon(
                            id = addon.getInt("id"),
                            name = addon.getString("name"),
                            selling_price = jsonNumberAsString(addon, "selling_price", "0"),
                            is_active = addon.optBoolean("is_active", true),
                        )
                    } catch (_: Exception) {
                        null
                    }
                }
                MenuAddonGroup(
                    id = group.getInt("id"),
                    name = group.getString("name"),
                    selection_type = group.optString("selection_type", "multiple"),
                    addons = addons,
                )
            } catch (_: Exception) {
                null
            }
        }
        return Product(
            id = item.getInt("id"),
            name = item.getString("name"),
            category = item.optInt("category").takeIf { item.has("category") && !item.isNull("category") },
            category_name = item.optString("category_name", null)
                ?.takeIf { it.isNotBlank() && it != "null" },
            selling_price = jsonNumberAsString(item, "selling_price", "0"),
            addon_groups = addonGroups,
        )
    }

    fun parseCategories(body: String): List<ProductCategory> {
        val json = org.json.JSONObject(body)
        val results = json.optJSONArray("results") ?: org.json.JSONArray()
        return (0 until results.length()).map { index ->
            val item = results.getJSONObject(index)
            ProductCategory(
                id = item.getInt("id"),
                name = item.getString("name"),
            )
        }
    }

    fun parseCurrencies(body: String): List<Currency> {
        val json = org.json.JSONObject(body)
        val results = json.optJSONArray("results") ?: org.json.JSONArray()
        return (0 until results.length()).map { index ->
            val item = results.getJSONObject(index)
            Currency(
                id = item.getInt("id"),
                code = item.optString("code", ""),
                name = item.getString("name"),
                symbol = item.optString("symbol", ""),
                is_base = item.optBoolean("is_base", false),
                is_active = item.optBoolean("is_active", true),
                current_rate = if (item.isNull("current_rate")) {
                    null
                } else {
                    jsonNumberAsString(item, "current_rate", "")
                        .takeIf { it.isNotBlank() && it != "null" }
                },
            )
        }
    }

    private fun parseOrder(json: org.json.JSONObject): KitchenOrder {
        val itemsJson = json.optJSONArray("items") ?: org.json.JSONArray()
        val items = (0 until itemsJson.length()).map { i ->
            val item = itemsJson.getJSONObject(i)
            val addonsJson = item.optJSONArray("addons") ?: org.json.JSONArray()
            val addons = (0 until addonsJson.length()).map { addonIndex ->
                val addon = addonsJson.getJSONObject(addonIndex)
                OrderItemAddon(
                    name = addon.getString("name"),
                    price = addon.optString("price", "0"),
                )
            }
            OrderItem(
                id = item.getInt("id"),
                product_name = item.getString("product_name"),
                quantity = item.optString("quantity", "0"),
                price = item.optString("price", "0"),
                notes = item.optString("notes", ""),
                addons = addons,
            )
        }
        val paymentsJson = json.optJSONArray("payments") ?: org.json.JSONArray()
        val payments = (0 until paymentsJson.length()).map { i ->
            val payment = paymentsJson.getJSONObject(i)
            OrderPaymentLine(
                method = payment.optString("method", "cash"),
                amount = payment.optString("amount", "0"),
                method_display = payment.optString("method_display", null),
                currency_name = payment.optString("currency_name", null),
                currency_symbol = payment.optString("currency_symbol", null),
            )
        }
        val fiscalInfo = parseFiscalReceiptInfo(
            json.optJSONObject("fiscal") ?: json.optJSONObject("fiscal_result"),
        )
        return KitchenOrder(
            id = json.getInt("id"),
            branch = json.getInt("branch"),
            branch_name = json.optString("branch_name", ""),
            order_type = json.optString("order_type", "takeaway"),
            table_number = json.optString("table_number", ""),
            total_amount = json.optString("total_amount", "0"),
            status = json.optString("status", "open"),
            kitchen_status = json.optString("kitchen_status", "pending"),
            created_by_name = json.optString("created_by_name", null),
            customer_name = json.optString("customer_name", null),
            created_at = json.optString("created_at", ""),
            items = items,
            branch_fiscalization_enabled = json.optBoolean("branch_fiscalization_enabled", false),
            customer = json.optInt("customer").takeIf { json.has("customer") && !json.isNull("customer") },
            payment_currency_name = json.optString("payment_currency_name", null),
            payment_currency_symbol = json.optString("payment_currency_symbol", null),
            amount_paid = json.optString("amount_paid", null),
            receipt_number = json.optString("receipt_number", null),
            fiscal_receipt_number = json.optString("fiscal_receipt_number", null)?.takeIf { it.isNotBlank() }
                ?: fiscalInfo?.invoiceNumber,
            fiscal = fiscalInfo,
            paid_by_name = json.optString("paid_by_name", null),
            fiscal_approval_status = json.optString("fiscal_approval_status", null)?.takeIf { it.isNotBlank() },
            payment_method = json.optString("payment_method", null),
            customer_account_balance = json.optString("customer_account_balance", null),
            payments = payments,
        )
    }

    private fun parseFiscalReceiptInfo(json: org.json.JSONObject?): FiscalReceiptInfo? {
        if (json == null) return null
        fun optText(vararg keys: String): String? {
            for (key in keys) {
                val value = json.optString(key, null)?.takeIf { it.isNotBlank() && it != "null" }
                if (value != null) return value
                if (json.has(key) && !json.isNull(key)) {
                    val raw = json.opt(key)
                    if (raw != null && raw != org.json.JSONObject.NULL) {
                        val text = raw.toString().trim()
                        if (text.isNotEmpty() && text != "null") return text
                    }
                }
            }
            return null
        }
        val info = FiscalReceiptInfo(
            invoiceNumber = optText("invoiceNumber", "fiscal_invoice_number", "invoice_no"),
            deviceBranchName = optText("deviceBranchName", "device_branch_name"),
            deviceSerialNo = optText("deviceSerialNo", "device_serial_no"),
            fiscalDayNumber = optText("fiscalDayNumber", "fiscal_day_number"),
            receiptCounter = optText("receiptCounter", "receipt_counter"),
            receiptGlobalNo = optText("receiptGlobalNo", "receipt_global_no"),
            verificationCode = optText("verificationCode", "verification_code"),
            qrUrl = optText("qrUrl", "qr_url"),
            qrString = optText("qrString", "qr_string"),
        )
        return if (
            info.invoiceNumber == null &&
            info.verificationCode == null &&
            info.qrUrl == null &&
            info.qrString == null &&
            info.deviceSerialNo == null
        ) {
            null
        } else {
            info
        }
    }

    fun parseSuppliers(body: String): List<Supplier> {
        val json = org.json.JSONObject(body)
        val results = json.optJSONArray("results") ?: org.json.JSONArray()
        return (0 until results.length()).map { index ->
            val item = results.getJSONObject(index)
            Supplier(
                id = item.getInt("id"),
                name = item.getString("name"),
                is_active = item.optBoolean("is_active", true),
            )
        }
    }

    fun parseCustomers(body: String): List<Customer> {
        val json = org.json.JSONObject(body)
        val results = json.optJSONArray("results") ?: org.json.JSONArray()
        return (0 until results.length()).map { index ->
            parseCustomerObject(results.getJSONObject(index))
        }
    }

    fun parseCustomer(body: String): Customer {
        return parseCustomerObject(org.json.JSONObject(body))
    }

    private fun parseCustomerObject(item: org.json.JSONObject): Customer {
        return Customer(
            id = item.getInt("id"),
            full_name = item.optString("full_name", item.optString("first_name", "Customer")),
            account_balance = jsonNumberAsString(item, "account_balance", "0"),
            credit_limit = jsonNumberAsString(item, "credit_limit", "0"),
            account_type = item.optString("account_type", "regular").ifBlank { "regular" },
        )
    }

    private fun jsonNumberAsString(
        json: org.json.JSONObject,
        key: String,
        fallback: String,
    ): String {
        if (!json.has(key) || json.isNull(key)) return fallback
        return when (val raw = json.get(key)) {
            is Number -> raw.toString()
            else -> raw.toString().ifBlank { fallback }
        }
    }

    fun parseDiningTables(body: String): List<DiningTable> {
        val json = org.json.JSONObject(body)
        val results = json.optJSONArray("results") ?: org.json.JSONArray()
        return (0 until results.length()).map { index ->
            val item = results.getJSONObject(index)
            DiningTable(
                id = item.getInt("id"),
                branch = item.getInt("branch"),
                name = item.getString("name"),
                sort_order = item.optInt("sort_order", 0),
                is_active = item.optBoolean("is_active", true),
            )
        }
    }

    fun parseDayEndStockTakeCheck(body: String): DayEndStockTakeCheck {
        val json = org.json.JSONObject(body)
        return DayEndStockTakeCheck(
            completed = json.optBoolean("completed", false),
            detail = json.optString("detail", ""),
            draftInProgress = json.optBoolean("draft_in_progress", false),
        )
    }

    fun parseFiscalDayStatus(body: String): FiscalDayStatus {
        val json = org.json.JSONObject(body)
        return FiscalDayStatus(
            fiscalDayStatus = json.optString("fiscal_day_status", ""),
            fiscalDayNumber = json.opt("fiscal_day_number").takeUnless { it == org.json.JSONObject.NULL },
            lastReceiptGlobalNo = json.opt("last_receipt_global_no").takeUnless { it == org.json.JSONObject.NULL },
            deviceId = json.optString("device_id", null)?.takeIf { it.isNotBlank() },
            branchId = if (json.has("branch_id") && !json.isNull("branch_id")) json.optInt("branch_id") else null,
            branchName = json.optString("branch_name", null)?.takeIf { it.isNotBlank() },
            canOpenDay = json.optBoolean("can_open_day", false),
            canCloseDay = json.optBoolean("can_close_day", false),
        )
    }

    fun parseFiscalisedSnapshot(body: String): FiscalisedSnapshot {
        val json = org.json.JSONObject(body)
        val meta = json.optJSONObject("meta") ?: org.json.JSONObject()
        val outputTax = json.optJSONObject("output_tax") ?: org.json.JSONObject()
        return FiscalisedSnapshot(
            count = meta.optInt("fiscalized_sales_count", 0),
            totalIncludingVat = outputTax.optString("total_sales_including_vat", "0"),
            vatAmount = outputTax.optString("vat_on_taxable_sales", "0"),
        )
    }

    fun parseDayEndReport(body: String): DayEndReportResponse {
        val json = org.json.JSONObject(body)
        val branch = json.getJSONObject("branch")
        val base = json.optJSONObject("base_currency")
        return DayEndReportResponse(
            branchName = branch.getString("name"),
            branchLocation = branch.optString("location", null),
            baseCurrencyCode = base?.optString("code", null),
            printedAt = json.optString("printed_at", ""),
            report = json.getJSONObject("report"),
        )
    }

    fun parseExpenses(body: String): List<Expense> {
        val json = org.json.JSONObject(body)
        val results = json.optJSONArray("results") ?: org.json.JSONArray()
        return (0 until results.length()).map { index ->
            val item = results.getJSONObject(index)
            Expense(
                id = item.getInt("id"),
                expenseDate = item.optString("expense_date", ""),
                amount = item.optString("amount", "0"),
                currencyCode = item.optString("currency_code", null)?.takeIf { it.isNotBlank() },
                currencyName = item.optString("currency_name", null)?.takeIf { it.isNotBlank() },
                currencySymbol = item.optString("currency_symbol", null)?.takeIf { it.isNotBlank() },
                description = item.optString("description", "Expense"),
                supplierName = item.optString("supplier_name", null)?.takeIf { it.isNotBlank() },
                recordedByName = item.optString("recorded_by_name", null)?.takeIf { it.isNotBlank() },
            )
        }
    }

    fun parseStockTakes(body: String): List<StockTake> {
        val json = org.json.JSONObject(body)
        val results = json.optJSONArray("results") ?: org.json.JSONArray()
        return (0 until results.length()).map { index ->
            parseStockTakeObject(results.getJSONObject(index))
        }
    }

    fun parseStockTake(body: String): StockTake {
        return parseStockTakeObject(org.json.JSONObject(body))
    }

    private fun parseStockTakeObject(json: org.json.JSONObject): StockTake {
        val linesJson = json.optJSONArray("lines") ?: org.json.JSONArray()
        val lines = (0 until linesJson.length()).map { index ->
            val line = linesJson.getJSONObject(index)
            val counted = if (line.isNull("counted_quantity")) {
                null
            } else {
                line.optString("counted_quantity", null)?.takeIf { it.isNotBlank() && it != "null" }
            }
            val systemQty = if (line.isNull("system_quantity")) {
                null
            } else {
                line.optString("system_quantity", null)?.takeIf { it.isNotBlank() && it != "null" }
            }
            val variance = if (line.isNull("variance")) {
                null
            } else {
                line.optString("variance", null)?.takeIf { it.isNotBlank() && it != "null" }
            }
            val wastage = if (line.isNull("wastage_quantity")) {
                "0"
            } else {
                line.optString("wastage_quantity", "0")
                    ?.takeIf { it.isNotBlank() && it != "null" } ?: "0"
            }
            StockTakeLine(
                id = line.getInt("id"),
                productId = line.optInt("product", 0),
                productName = line.optString("product_name", "Product"),
                categoryName = line.optString("category_name", null)
                    ?.takeIf { it.isNotBlank() && it != "null" },
                stockTakeStation = line.optString("stock_take_station", "shop")
                    .takeIf { it.isNotBlank() && it != "null" } ?: "shop",
                stockTakeStationDisplay = line.optString("stock_take_station_display", "Shop")
                    .takeIf { it.isNotBlank() && it != "null" } ?: "Shop",
                systemQuantity = systemQty,
                countedQuantity = counted,
                wastageQuantity = wastage,
                variance = variance,
                notes = line.optString("notes", ""),
            )
        }
        val status = json.optString("status", "draft")
        return StockTake(
            id = json.getInt("id"),
            stockTakeType = json.optString("stock_take_type", "daily"),
            stockTakeTypeDisplay = json.optString(
                "stock_take_type_display",
                json.optString("stock_take_type", "Daily"),
            ),
            status = status,
            statusDisplay = json.optString("status_display", status.replaceFirstChar { it.uppercase() }),
            countDate = json.optString("count_date", ""),
            branchName = json.optString("branch_name", ""),
            createdAt = json.optString("created_at", ""),
            completedAt = json.optString("completed_at", null)
                ?.takeIf { it.isNotBlank() && it != "null" },
            lineCount = json.optInt("line_count", lines.size),
            varianceCount = json.optInt("variance_count", 0),
            lines = lines,
        )
    }

    fun parseCustomerStatement(body: String, allTime: Boolean = false): CustomerStatement {
        val json = org.json.JSONObject(body)
        val period = json.optJSONObject("period")
        val periodFrom = period?.optString("from", null)?.takeIf { it.isNotBlank() && it != "null" }
        val periodTo = period?.optString("to", null)?.takeIf { it.isNotBlank() && it != "null" }
        val txnsJson = json.optJSONArray("transactions") ?: org.json.JSONArray()
        val transactions = (0 until txnsJson.length()).map { index ->
            val item = txnsJson.getJSONObject(index)
            val orderId = if (item.has("order_id") && !item.isNull("order_id")) {
                item.optInt("order_id").takeIf { it > 0 }
            } else {
                null
            }
            CustomerStatementTransaction(
                id = item.getInt("id"),
                statementLabel = item.optString(
                    "statement_label",
                    item.optString("transaction_type_display", "Transaction"),
                ),
                transactionType = item.optString("transaction_type", ""),
                amount = jsonNumberAsString(item, "amount", "0"),
                balanceAfter = jsonNumberAsString(item, "balance_after", "0"),
                currencyCode = item.optString("currency_code", null)?.takeIf { it.isNotBlank() },
                currencyName = item.optString("currency_name", null)?.takeIf { it.isNotBlank() },
                currencySymbol = item.optString("currency_symbol", null)?.takeIf { it.isNotBlank() },
                amountReceived = if (item.has("amount_received") && !item.isNull("amount_received")) {
                    jsonNumberAsString(item, "amount_received", "0")
                } else {
                    null
                },
                orderId = orderId,
                notes = item.optString("notes", ""),
                recordedByName = item.optString("recorded_by_name", null)
                    ?.takeIf { it.isNotBlank() }
                    ?: item.optString("recorded_by_username", null)?.takeIf { it.isNotBlank() },
                createdAt = item.optString("created_at", ""),
                isBalanceAdjustment = item.optBoolean("is_balance_adjustment", false)
                    || item.optString("transaction_type", "") == "adjustment",
            )
        }
        return CustomerStatement(
            customerId = json.optInt("customer_id", 0),
            periodFrom = periodFrom,
            periodTo = periodTo,
            allTime = allTime || (periodFrom == null && periodTo == null),
            openingBalance = jsonNumberAsString(json, "opening_balance", "0"),
            closingBalance = jsonNumberAsString(json, "closing_balance", "0"),
            currentBalance = jsonNumberAsString(json, "current_balance", "0"),
            totalCredits = jsonNumberAsString(json, "total_credits", "0"),
            totalDebits = jsonNumberAsString(json, "total_debits", "0"),
            transactionCount = json.optInt("transaction_count", transactions.size),
            transactions = transactions,
        )
    }

    fun parseCustomerDeposit(body: String): CustomerDepositResult {
        val json = org.json.JSONObject(body)
        val transaction = json.optJSONObject("transaction")
            ?: throw IllegalArgumentException(
                "Server did not confirm the deposit. Check the app server URL matches the portal.",
            )
        val transactionId = transaction.optInt("id", 0)
        if (transactionId <= 0) {
            throw IllegalArgumentException(
                "Server did not confirm the deposit. Check the app server URL matches the portal.",
            )
        }
        val balance = when {
            json.isNull("account_balance") -> transaction.optString("balance_after", "0")
            else -> {
                val raw = json.get("account_balance")
                when (raw) {
                    is Number -> raw.toString()
                    else -> raw.toString()
                }
            }
        }
        val amount = if (transaction.isNull("amount")) {
            null
        } else {
            when (val raw = transaction.get("amount")) {
                is Number -> raw.toString()
                else -> raw.toString()
            }
        }
        return CustomerDepositResult(
            accountBalance = balance,
            transactionId = transactionId,
            amount = amount,
        )
    }
}
