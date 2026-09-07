package com.naveenhospital.medtrack.core.data.local

import com.naveenhospital.medtrack.core.network.model.CallLogDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [24])
class CallLogMappingTest {
    @Test
    fun timezoneOffsetsReferToTheSameMicrosecond() {
        assertEquals(1L, receiptEpochMicros("1970-01-01T00:00:00.000001Z"))
        assertEquals(1L, receiptEpochMicros("1970-01-01T05:30:00.000001+05:30"))
        assertEquals(1L, receiptEpochMicros("1969-12-31T20:00:00.000001-04:00"))
        assertEquals(0L, receiptEpochMicros("1970-01-01T00:00:00+00:00"))
    }

    @Test
    fun fractionalPrecisionPreservesOrderingWithinOneMillisecond() {
        val first = receiptEpochMicros("2026-09-07T22:46:07.123001Z")
        val second = receiptEpochMicros("2026-09-07T22:46:07.123002Z")
        assertEquals(1L, second - first)
        assertTrue(second > first)
        assertEquals(receiptEpochMicros("2026-09-07T22:46:07.100000Z"), receiptEpochMicros("2026-09-07T22:46:07.1Z"))
        assertEquals(first, receiptEpochMicros("2026-09-07T22:46:07.123001999Z"))
    }

    @Test
    fun preEpochFractionsAndCalendarBoundariesRemainExact() {
        assertEquals(-1L, receiptEpochMicros("1969-12-31T23:59:59.999999Z"))
        assertEquals(951_782_400_000_000L, receiptEpochMicros("2000-02-29T00:00:00Z"))
        assertEquals(253_402_300_799_999_999L, receiptEpochMicros("9999-12-31T23:59:59.999999Z"))
    }

    @Test
    fun invalidDatesOffsetsAndPartialTimestampsAreRejected() {
        listOf(
            "", "2026-09-07", "2026-09-07T22:46:07", "2026-09-07T22:46:07Z trailing",
            "1900-02-29T00:00:00Z", "2026-02-30T00:00:00Z", "2026-13-01T00:00:00Z",
            "2026-09-07T24:00:00Z", "2026-09-07T22:60:00Z", "2026-09-07T22:46:60Z",
            "2026-09-07T22:46:07+18:01", "2026-09-07T22:46:07+05:60", "0000-01-01T00:00:00Z",
        ).forEach { timestamp ->
            assertTrue(timestamp, runCatching { receiptEpochMicros(timestamp) }.exceptionOrNull() is IllegalArgumentException)
        }
    }

    @Test
    fun mapperKeepsOriginalReceiptAndAccountIdentityOnApi24() {
        val receipt = "1970-01-01T05:30:00.000001+05:30"
        val dto = CallLogDto(id = 7, taskId = null, outcome = "REACHED", outcomeLabel = "Reached",
            notes = null, reason = "Appointment", createdAt = receipt)
        val entity = dto.toEntity("account-a", "42")
        assertEquals(1L, entity.createdAtEpochMicros)
        assertEquals("account-a", entity.ownerAccountId)
        assertEquals("42", entity.caseId)
        assertEquals(receipt, entity.toDomain().createdAt)
        assertEquals(1L, entity.toDomain().createdAtEpochMicros)
        assertEquals("Appointment", entity.toDomain().reason)
    }
}
