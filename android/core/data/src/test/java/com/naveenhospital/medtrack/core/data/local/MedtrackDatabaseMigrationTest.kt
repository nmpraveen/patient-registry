package com.naveenhospital.medtrack.core.data.local

import androidx.room.testing.MigrationTestHelper
import androidx.sqlite.db.framework.FrameworkSQLiteOpenHelperFactory
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class MedtrackDatabaseMigrationTest {
    @get:Rule
    val helper = MigrationTestHelper(
        InstrumentationRegistry.getInstrumentation(),
        MedtrackDatabase::class.java,
        emptyList(),
        FrameworkSQLiteOpenHelperFactory(),
    )

    // Room 2.8 compares the configured name with the opened path. An absolute
    // name works on both Android/Linux and Windows Robolectric sandboxes.
    private fun databasePath(name: String): String =
        InstrumentationRegistry.getInstrumentation().targetContext.getDatabasePath(name).absolutePath

    @Test
    fun identityUpgradePreservesOwnedCasesAndLegacyOutboxBytes() {
        val name = databasePath("stage3_14_to_15")
        val payload = """{"use_temporary_uhid":true,"uhid":"TMP-LEGACY","client_write_id":"legacy-id"}"""
        helper.createDatabase(name, 14).use { db ->
            for (owner in listOf("a", "b")) {
                db.execSQL("INSERT INTO cases (ownerAccountId,id,uhid,patientName,category,status,diagnosis,isHighRisk,highRiskReasons,updatedAtMillis) VALUES (?,'42','TMP-LEGACY','Synthetic','Medicine','ACTIVE','Review',0,'',1)", arrayOf(owner))
                db.execSQL("INSERT INTO pending_writes (ownerAccountId,clientWriteId,writeType,caseId,taskId,payloadJson,retryCount,lastError,createdAtMillis,updatedAtMillis) VALUES (?,'legacy-id','call_outcome','42',NULL,?,2,NULL,1,2)", arrayOf(owner, payload))
            }
        }
        helper.runMigrationsAndValidate(name, 15, true, *MedtrackDatabase.ALL_MIGRATIONS).use { db ->
            db.query("SELECT ownerAccountId,mtno,uhid FROM cases ORDER BY ownerAccountId").use { cursor ->
                assertEquals(2, cursor.count)
                for (owner in listOf("a", "b")) {
                    assertTrue(cursor.moveToNext())
                    assertEquals(owner, cursor.getString(0))
                    assertEquals("", cursor.getString(1))
                    assertEquals("TMP-LEGACY", cursor.getString(2))
                }
            }
            db.query("SELECT payloadJson,retryCount FROM pending_writes").use { cursor ->
                assertEquals(2, cursor.count)
                while (cursor.moveToNext()) {
                    assertEquals(payload, cursor.getString(0))
                    assertEquals(2, cursor.getInt(1))
                }
            }
        }
    }

    @Test
    fun stage2UpgradePreservesOwnedPendingBytesAndTaskNotes() {
        val name = databasePath("stage2_13_to_14")
        val json = """{"client_write_id":"legacy-call","outcome":"attempted"}"""
        helper.createDatabase(name, 13).use { db ->
            db.execSQL("INSERT INTO pending_writes (ownerAccountId, clientWriteId, writeType, caseId, taskId, payloadJson, retryCount, lastError, createdAtMillis, updatedAtMillis) VALUES ('a','legacy-call','call_outcome','42',NULL,?,2,NULL,1,2)", arrayOf(json))
            db.execSQL("INSERT INTO tasks (ownerAccountId,id,caseId,title,dueDate,status,statusLabel,canComplete,notes,updatedAtMillis) VALUES ('a','7','42','Review','2026-09-08','SCHEDULED','Scheduled',1,'Keep notes',1)")
        }
        helper.runMigrationsAndValidate(name, 14, true, *MedtrackDatabase.ALL_MIGRATIONS).use { db ->
            db.query("SELECT payloadJson,retryCount FROM pending_writes WHERE ownerAccountId='a'").use { cursor ->
                assertTrue(cursor.moveToFirst()); assertEquals(json,cursor.getString(0)); assertEquals(2,cursor.getInt(1))
            }
            db.query("SELECT notes,frequencyLabel,serverUpdatedAt FROM tasks WHERE ownerAccountId='a'").use { cursor ->
                assertTrue(cursor.moveToFirst()); assertEquals("Keep notes",cursor.getString(0)); assertEquals("",cursor.getString(1)); assertEquals("",cursor.getString(2))
            }
        }
    }

    @Test
    fun everySupportedSchemaVersionMigratesToCurrentSchema() {
        (1..14).forEach { startVersion ->
            val databaseName = databasePath("migration_${startVersion}_to_15")
            helper.createDatabase(databaseName, startVersion).close()

            helper.runMigrationsAndValidate(
                databaseName,
                15,
                true,
                *MedtrackDatabase.ALL_MIGRATIONS,
            ).use { database ->
                database.query("PRAGMA user_version").use { cursor ->
                    assertTrue(cursor.moveToFirst())
                    assertEquals(15, cursor.getInt(0))
                }
            }
        }
    }

    @Test
    fun ownershipTransitionDropsUnownedOutboxAndAcceptsSameKeyForTwoAccounts() {
        val databaseName = databasePath("migration_ownership_transition")
        helper.createDatabase(databaseName, 10).use { database ->
            database.execSQL(
                """
                INSERT INTO pending_writes (
                    clientWriteId, writeType, caseId, taskId, payloadJson,
                    retryCount, lastError, createdAtMillis, updatedAtMillis
                ) VALUES ('shared-write', 'task_complete', '42', '7', '{}', 0, NULL, 1, 1)
                """.trimIndent(),
            )
        }

        helper.runMigrationsAndValidate(
            databaseName,
            14,
            true,
            *MedtrackDatabase.ALL_MIGRATIONS,
        ).use { database ->
            database.query("SELECT COUNT(*) FROM pending_writes").use { cursor ->
                assertTrue(cursor.moveToFirst())
                assertEquals(0, cursor.getInt(0))
            }

            listOf("account-a", "account-b").forEach { ownerAccountId ->
                database.execSQL(
                    """
                    INSERT INTO pending_writes (
                        ownerAccountId, clientWriteId, writeType, caseId, taskId,
                        payloadJson, retryCount, lastError, createdAtMillis, updatedAtMillis
                    ) VALUES (?, 'shared-write', 'task_complete', '42', '7', '{}', 0, NULL, 2, 2)
                    """.trimIndent(),
                    arrayOf(ownerAccountId),
                )
            }

            database.query(
                "SELECT ownerAccountId FROM pending_writes ORDER BY ownerAccountId",
            ).use { cursor ->
                assertEquals(2, cursor.count)
                assertTrue(cursor.moveToFirst())
                assertEquals("account-a", cursor.getString(0))
                assertTrue(cursor.moveToNext())
                assertEquals("account-b", cursor.getString(0))
            }
        }
    }

    @Test
    fun lifecycleUpgradePreservesV11OwnedRowsButRequiresFreshActivation() {
        val databaseName = databasePath("migration_11_to_14_owned_rows")
        helper.createDatabase(databaseName, 11).use { database ->
            database.execSQL(
                """
                INSERT INTO pending_writes (
                    ownerAccountId, clientWriteId, writeType, caseId, taskId,
                    payloadJson, retryCount, lastError, createdAtMillis, updatedAtMillis
                ) VALUES ('account-a', 'owned-write', 'task_complete', '42', '7', '{}', 0, NULL, 2, 2)
                """.trimIndent(),
            )
        }

        helper.runMigrationsAndValidate(
            databaseName,
            14,
            true,
            *MedtrackDatabase.ALL_MIGRATIONS,
        ).use { database ->
            database.query("SELECT ownerAccountId, clientWriteId FROM pending_writes").use { cursor ->
                assertTrue(cursor.moveToFirst())
                assertEquals("account-a", cursor.getString(0))
                assertEquals("owned-write", cursor.getString(1))
            }
            database.query("SELECT COUNT(*) FROM account_lifecycle").use { cursor ->
                assertTrue(cursor.moveToFirst())
                assertEquals(0, cursor.getInt(0))
            }
        }
    }
}
