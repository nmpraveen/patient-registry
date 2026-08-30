package com.naveenhospital.medtrack.core.push

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class OpaquePushPolicyTest {
    @Test
    fun `background push with PHI never displays or forwards payload`() {
        val policy = policyForOpaquePush(
            untrustedData = mapOf(
                "patient_name" to "Jane Patient",
                "uhid" to "UHID-SECRET",
                "phone_number" to "7345551212",
                "case_id" to "42",
                "body" to "Jane Patient needs surgery",
            ),
            untrustedTitle = "Jane Patient",
            untrustedBody = "Call 7345551212",
            accountMatches = true,
            sessionAuthorized = true,
            networkAvailable = true,
        )

        assertFalse(policy.enqueueAuthenticatedRefresh)
        assertFalse(policy.displaySystemNotification)
        assertFalse(policy.forwardPayloadToIntent)
    }

    @Test
    fun `offline logout uncertainty suppresses display`() {
        val policy = policyForOpaquePush(
            untrustedData = mapOf("event_id" to "11111111-1111-4111-8111-111111111111"),
            untrustedTitle = null,
            untrustedBody = null,
            accountMatches = null,
            sessionAuthorized = false,
            networkAvailable = false,
        )

        assertTrue(policy.enqueueAuthenticatedRefresh)
        assertFalse(policy.displaySystemNotification)
        assertFalse(policy.forwardPayloadToIntent)
    }

    @Test
    fun `account switch mismatch suppresses stale account display`() {
        val policy = policyForOpaquePush(
            untrustedData = mapOf("event_id" to "22222222-2222-4222-8222-222222222222"),
            untrustedTitle = null,
            untrustedBody = null,
            accountMatches = false,
            sessionAuthorized = true,
            networkAvailable = true,
        )

        assertTrue(policy.enqueueAuthenticatedRefresh)
        assertFalse(policy.displaySystemNotification)
        assertFalse(policy.forwardPayloadToIntent)
    }

    @Test
    fun `noncanonical UUID envelope is rejected`() {
        val policy = policyForOpaquePush(
            untrustedData = mapOf("event_id" to "1-1-1-1-1"),
            untrustedTitle = null,
            untrustedBody = null,
            accountMatches = true,
            sessionAuthorized = true,
            networkAvailable = true,
        )

        assertFalse(policy.enqueueAuthenticatedRefresh)
        assertFalse(policy.displaySystemNotification)
        assertFalse(policy.forwardPayloadToIntent)
    }
}
