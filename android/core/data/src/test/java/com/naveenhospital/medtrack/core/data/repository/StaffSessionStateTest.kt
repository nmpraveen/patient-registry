package com.naveenhospital.medtrack.core.data.repository

import com.naveenhospital.medtrack.core.data.auth.AccountSessionIdentity
import com.naveenhospital.medtrack.core.domain.model.DirectoryPhone
import com.naveenhospital.medtrack.core.domain.model.dialNumber
import kotlinx.coroutines.CancellationException
import org.junit.Assert.*
import org.junit.Test

class StaffSessionStateTest {
    private val first = AccountSessionIdentity("1", "first")

    @Test fun lateResponseAfterLogoutCannotRestoreData() {
        val store = StaffSessionState<List<String>>(emptyList())
        store.activate(first)
        val request = store.begin(first)
        store.activate(null)
        assertFalse(store.publish(first, request, listOf("old")))
        assertTrue(store.state.value.isEmpty())
    }

    @Test fun sameAccountNewLoginRejectsPreviousIncarnation() {
        val store = StaffSessionState<List<String>>(emptyList())
        store.activate(first)
        val request = store.begin(first)
        store.activate(first.copy(incarnation = "second"))
        assertFalse(store.publish(first, request, listOf("old")))
        assertThrows(CancellationException::class.java) { store.begin(first) }
    }

    @Test fun latestSearchWinsAndRefreshClearsStaleRows() {
        val store = StaffSessionState<List<String>>(emptyList())
        store.activate(first)
        val old = store.begin(first)
        assertTrue(store.publish(first, old, listOf("obsolete")))
        val fresh = store.begin(first)
        assertTrue(store.state.value.isEmpty())
        assertFalse(store.publish(first, old, listOf("late")))
        assertTrue(store.publish(first, fresh, listOf("current")))
        assertEquals(listOf("current"), store.state.value)
    }

    @Test fun dialerRejectsCommandsAndKeepsExtensionSeparate() {
        assertEquals("+911234567890", DirectoryPhone("Desk", "+91 (123) 456-7890", "22").dialNumber())
        for (value in listOf("tel:1234", "*123#", "123;456", "123,456", "12", "")) {
            assertNull(DirectoryPhone("", value, "").dialNumber())
        }
    }
}
