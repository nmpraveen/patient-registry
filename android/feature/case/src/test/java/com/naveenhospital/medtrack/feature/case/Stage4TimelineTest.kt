package com.naveenhospital.medtrack.feature.cases

import org.junit.Assert.*
import org.junit.Test
import java.util.Locale
import java.util.TimeZone

class Stage4TimelineTest {
    @Test fun timestampUsesHospitalTimezoneAcrossMidnightAndRetainsInput() {
        val locale = Locale.getDefault()
        val zone = TimeZone.getDefault()
        try {
            Locale.setDefault(Locale.US)
            TimeZone.setDefault(TimeZone.getTimeZone("Pacific/Honolulu"))
            val source = "2026-12-31T23:59:59.123456Z"
            assertTrue(timelineTimestamp(source, "Asia/Kolkata").startsWith("01 Jan 2027, 05:29"))
            assertEquals("2026-12-31T23:59:59.123456Z", source)
            assertTrue(timelineTimestamp("2027-01-01T05:29:59.123456+05:30", "Asia/Kolkata").startsWith("01 Jan 2027, 05:29"))
            assertEquals("unknown", timelineTimestamp("unknown", "Asia/Kolkata"))
        } finally {
            Locale.setDefault(locale)
            TimeZone.setDefault(zone)
        }
    }
}
