package com.naveenhospital.medtrack.core.data.repository

import com.naveenhospital.medtrack.core.domain.model.UpcomingTask
import com.naveenhospital.medtrack.core.domain.model.groupUpcomingTasks
import com.naveenhospital.medtrack.core.domain.model.shiftUpcomingDate
import org.junit.Assert.*
import org.junit.Test
import java.util.TimeZone

class Stage4PresentationTest {
    private fun task(id: Long, caseId: Long = 4, date: String = "2026-12-31") =
        UpcomingTask(id, caseId, "Synthetic patient", "Medicine", "Review", date, "Staff")

    @Test fun groupsAcrossPagesKeepDistinctSameTitleTasksAndSeparateCasesAndDates() {
        val first = listOf(task(2), task(1))
        val second = listOf(task(2), task(3), task(4, caseId = 5), task(5, date = "2027-01-01"))
        val grouped = groupUpcomingTasks(first + second)
        assertEquals(listOf("2026-12-31:4", "2026-12-31:5", "2027-01-01:4"), grouped.map { it.key })
        assertEquals(listOf(1L, 2L, 3L), grouped.first().tasks.map { it.id })
        assertEquals(5, grouped.sumOf { it.tasks.size })
    }

    @Test fun weekWindowsCrossYearLeapDayAndDstWithoutChangingClinicalDates() {
        val original = TimeZone.getDefault()
        try {
            for (zone in listOf("America/New_York", "Pacific/Kiritimati", "Pacific/Honolulu")) {
                TimeZone.setDefault(TimeZone.getTimeZone(zone))
                assertEquals("2027-01-05", shiftUpcomingDate("2026-12-29", 7))
                assertEquals("2028-03-01", shiftUpcomingDate("2028-02-23", 7))
                assertEquals("2026-03-12", shiftUpcomingDate("2026-03-05", 7))
                assertEquals("2026-10-29", shiftUpcomingDate("2026-11-05", -7))
            }
        } finally { TimeZone.setDefault(original) }
        assertNull(shiftUpcomingDate("2026-02-29", 7))
        assertNull(shiftUpcomingDate("2026-01-01T00:00:00Z", 7))
    }
}
