package com.naveenhospital.medtrack.core.push

import org.junit.Assert.assertEquals
import org.junit.Test

class MedtrackPushTest {
    @Test
    fun channelForTypeMapsServerNotificationTypesToV1Channels() {
        assertEquals(MedtrackPush.CHANNEL_ASSIGNMENTS, MedtrackPush.channelForType("assignment"))
        assertEquals(MedtrackPush.CHANNEL_RED_FLAGS, MedtrackPush.channelForType("red_flag"))
        assertEquals(MedtrackPush.CHANNEL_OVERDUE, MedtrackPush.channelForType("overdue"))
    }

    @Test
    fun channelForTypeAcceptsChannelAliasesFromPayloads() {
        assertEquals(MedtrackPush.CHANNEL_ASSIGNMENTS, MedtrackPush.channelForType("assignments"))
        assertEquals(MedtrackPush.CHANNEL_RED_FLAGS, MedtrackPush.channelForType("red_flags"))
    }

    @Test
    fun channelForTypeFallsBackToOverdueForUnknownOrMissingType() {
        assertEquals(MedtrackPush.CHANNEL_OVERDUE, MedtrackPush.channelForType(null))
        assertEquals(MedtrackPush.CHANNEL_OVERDUE, MedtrackPush.channelForType(""))
        assertEquals(MedtrackPush.CHANNEL_OVERDUE, MedtrackPush.channelForType("unexpected"))
    }
}
