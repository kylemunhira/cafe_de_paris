package com.cafedeparis.kitchen.data

data class TaxBreakdown(
    val subtotal: Double,
    val tax: Double,
    val taxRate: Double,
    val zta: Double,
    val ztaRate: Double,
    val goodsTotal: Double,
    val total: Double,
)

object TaxMath {
    fun roundMoney(amount: Double): Double = Math.round(amount * 100.0) / 100.0

    fun splitInclusiveTotal(
        inclusiveTotal: Double,
        taxRate: Double = 15.5,
        applyZta: Boolean = false,
        ztaRate: Double = 2.0,
    ): TaxBreakdown {
        val goodsTotal = roundMoney(inclusiveTotal)
        val divisor = 1.0 + taxRate / 100.0
        val subtotal = roundMoney(goodsTotal / divisor)
        val tax = roundMoney(goodsTotal - subtotal)
        val appliedZtaRate = if (applyZta) ztaRate else 0.0
        val zta = if (applyZta) roundMoney(subtotal * appliedZtaRate / 100.0) else 0.0
        val displayedSubtotal = if (applyZta) roundMoney(subtotal - zta) else subtotal
        return TaxBreakdown(
            subtotal = displayedSubtotal,
            tax = tax,
            taxRate = taxRate,
            zta = zta,
            ztaRate = appliedZtaRate,
            goodsTotal = goodsTotal,
            total = goodsTotal,
        )
    }
}
