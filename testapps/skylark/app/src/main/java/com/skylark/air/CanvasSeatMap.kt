package com.skylark.air

import android.graphics.Paint
import android.graphics.Typeface
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.positionInWindow
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.unit.dp

/**
 * Layout variant 6: the seat map drawn on a Canvas, like the custom-drawn maps of many real apps. It has no
 * accessibility nodes at all (no seats in the tree, no labels, no IDs): a phone agent has to find a seat by looking at
 * the screen. The bottom bar ("Selected: 21A", "Confirm seat") stays a normal view, so a step's result is still
 * checkable from the tree.
 *
 * For exact checks of visual grounding, the drawn rectangles of the seats are published through the state hook
 * (`content query`, key `seat_rects`, screen pixels), with the visible part of the map (`seat_viewport`).
 */
private val LETTERS = listOf("A", "B", "C", "D", "E", "F")

private class SeatGeometry(width: Float, private val px: Float, private val rows: List<Int>) {
    val seat = 40 * px
    val gap = 6 * px
    val aisle = 20 * px
    val label = 32 * px
    val rowH = 52 * px
    private val left = (width - (label + 6 * seat + 5 * gap + aisle)) / 2

    fun rect(rowIndex: Int, col: Int): Rect {
        val x = left + label + col * (seat + gap) + (if (col >= 3) aisle else 0f)
        val y = rowIndex * rowH + (rowH - seat) / 2
        return Rect(x, y, x + seat, y + seat)
    }

    fun labelAt(rowIndex: Int) = Offset(left + label / 2, rowIndex * rowH + rowH / 2)

    fun seatAt(p: Offset): String? {
        for ((ri, row) in rows.withIndex()) for (c in 0 until 6) if (rect(ri, c).contains(p)) return "$row${LETTERS[c]}"
        return null
    }

    val height get() = rows.size * rowH
}

@Composable
fun CanvasSeatMap(s: AppState, trip: Trip, selected: String?, onSelect: (String) -> Unit) {
    val sm = s.seatMap
    val rows = (sm.firstRow..sm.lastRow).toList()
    val px = LocalDensity.current.density
    val view = LocalView.current
    val scroll = rememberScrollState()
    val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { textAlign = Paint.Align.CENTER; typeface = Typeface.DEFAULT }
    Column(
        Modifier.fillMaxSize()
            .onGloballyPositioned { c ->
                val p = c.positionInWindow()
                val loc = IntArray(2).also { view.getLocationOnScreen(it) }
                Store.seatViewport = intArrayOf(p.x.toInt() + loc[0], p.y.toInt() + loc[1], p.x.toInt() + loc[0] + c.size.width, p.y.toInt() + loc[1] + c.size.height)
            }
            .verticalScroll(scroll)
            .padding(12.dp),
    ) {
        Text("A and F are windows. C and D are aisles. Rows ${sm.paidRows.joinToString(" and ")} have extra legroom for $${sm.paidPrice}.", color = Color.Gray)
        Spacer(Modifier.height(8.dp))
        Canvas(
            Modifier.fillMaxWidth().height((rows.size * 52).dp)
                .onGloballyPositioned { c ->
                    val p = c.positionInWindow()
                    val loc = IntArray(2).also { view.getLocationOnScreen(it) }
                    val g = SeatGeometry(c.size.width.toFloat(), px, rows)
                    val out = HashMap<String, IntArray>()
                    for ((ri, row) in rows.withIndex()) for (col in 0 until 6) {
                        val r = g.rect(ri, col)
                        out["$row${LETTERS[col]}"] = intArrayOf((p.x + r.left).toInt() + loc[0], (p.y + r.top).toInt() + loc[1], (p.x + r.right).toInt() + loc[0], (p.y + r.bottom).toInt() + loc[1])
                    }
                    Store.seatRects = out
                }
                .pointerInput(rows, selected, sm.occupied, trip.flight.seat) {
                    detectTapGestures { p ->
                        val seat = SeatGeometry(size.width.toFloat(), px, rows).seatAt(p) ?: return@detectTapGestures
                        if (seat != trip.flight.seat && seat !in sm.occupied) onSelect(seat)
                    }
                },
        ) {
            val g = SeatGeometry(size.width, px, rows)
            for ((ri, row) in rows.withIndex()) {
                val lp = g.labelAt(ri)
                paint.color = Color.Gray.toArgb(); paint.textSize = 14 * px
                drawContext.canvas.nativeCanvas.drawText("$row", lp.x, lp.y + 5 * px, paint)
                for (col in 0 until 6) {
                    val seat = "$row${LETTERS[col]}"
                    val mine = seat == trip.flight.seat
                    val taken = seat in sm.occupied && !mine
                    val color = when { mine -> SkyLarkBlue; seat == selected -> Color(0xFF2E9E57); taken -> Color(0xFFBDBDBD); row in sm.paidRows -> Color(0xFFF2C14E); else -> Color(0xFFDCE8F5) }
                    val r = g.rect(ri, col)
                    drawRoundRect(color, topLeft = r.topLeft, size = Size(r.width, r.height), cornerRadius = CornerRadius(6 * px, 6 * px))
                    paint.color = (if (mine) Color.White else Color.Black).toArgb(); paint.textSize = 12 * px
                    drawContext.canvas.nativeCanvas.drawText(LETTERS[col], r.center.x, r.center.y + 4 * px, paint)
                }
            }
        }
    }
}
