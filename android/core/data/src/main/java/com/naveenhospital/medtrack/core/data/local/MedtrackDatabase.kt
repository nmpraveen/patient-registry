package com.naveenhospital.medtrack.core.data.local

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

@Database(
    entities = [
        CaseEntity::class,
        CaseStatsEntity::class,
        TaskEntity::class,
        VitalEntity::class,
        VitalsThresholdEntity::class,
        CategoryOptionsEntity::class,
        NotificationEntity::class,
        PushTokenEntity::class,
        PendingWriteEntity::class,
        SyncConflictEntity::class,
        CacheMetadataEntity::class,
    ],
    version = 9,
    exportSchema = true,
)
abstract class MedtrackDatabase : RoomDatabase() {
    abstract fun caseDao(): CaseDao
    abstract fun caseStatsDao(): CaseStatsDao
    abstract fun taskDao(): TaskDao
    abstract fun vitalDao(): VitalDao
    abstract fun vitalsThresholdDao(): VitalsThresholdDao
    abstract fun categoryOptionsDao(): CategoryOptionsDao
    abstract fun notificationDao(): NotificationDao
    abstract fun pushTokenDao(): PushTokenDao
    abstract fun pendingWriteDao(): PendingWriteDao
    abstract fun syncConflictDao(): SyncConflictDao
    abstract fun cacheMetadataDao(): CacheMetadataDao

    companion object {
        @Volatile
        private var INSTANCE: MedtrackDatabase? = null

        fun build(context: Context): MedtrackDatabase =
            INSTANCE ?: synchronized(this) {
                INSTANCE ?: Room.databaseBuilder(
                    context.applicationContext,
                    MedtrackDatabase::class.java,
                    "medtrack.db",
                )
                    .addMigrations(
                        MIGRATION_1_2,
                        MIGRATION_2_3,
                        MIGRATION_3_4,
                        MIGRATION_4_5,
                        MIGRATION_5_6,
                        MIGRATION_6_7,
                        MIGRATION_7_8,
                        MIGRATION_8_9,
                    )
                    .build()
                    .also { INSTANCE = it }
            }

        private val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE cases ADD COLUMN subcategoryValue TEXT")
            }
        }

        private val MIGRATION_2_3 = object : Migration(2, 3) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS tasks (
                        id TEXT NOT NULL PRIMARY KEY,
                        caseId TEXT NOT NULL,
                        title TEXT NOT NULL,
                        dueDate TEXT,
                        status TEXT NOT NULL,
                        statusLabel TEXT NOT NULL,
                        canComplete INTEGER NOT NULL,
                        updatedAtMillis INTEGER NOT NULL
                    )
                    """.trimIndent(),
                )
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS vitals (
                        id TEXT NOT NULL PRIMARY KEY,
                        caseId TEXT NOT NULL,
                        recordedAt TEXT NOT NULL,
                        bpSystolic INTEGER,
                        bpDiastolic INTEGER,
                        pulse INTEGER,
                        spo2 INTEGER,
                        weightKg TEXT,
                        hemoglobin TEXT,
                        summary TEXT NOT NULL,
                        updatedAtMillis INTEGER NOT NULL
                    )
                    """.trimIndent(),
                )
            }
        }

        private val MIGRATION_3_4 = object : Migration(3, 4) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS vitals_thresholds (
                        id TEXT NOT NULL PRIMARY KEY,
                        payloadJson TEXT NOT NULL,
                        updatedAtMillis INTEGER NOT NULL
                    )
                    """.trimIndent(),
                )
            }
        }

        private val MIGRATION_4_5 = object : Migration(4, 5) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS sync_conflicts (
                        clientWriteId TEXT NOT NULL PRIMARY KEY,
                        writeType TEXT NOT NULL,
                        caseId TEXT,
                        taskId TEXT,
                        message TEXT NOT NULL,
                        serverPayloadJson TEXT,
                        createdAtMillis INTEGER NOT NULL
                    )
                    """.trimIndent(),
                )
            }
        }

        private val MIGRATION_5_6 = object : Migration(5, 6) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS cache_metadata (
                        cacheKey TEXT NOT NULL PRIMARY KEY,
                        updatedAtMillis INTEGER NOT NULL
                    )
                    """.trimIndent(),
                )
            }
        }

        private val MIGRATION_6_7 = object : Migration(6, 7) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS case_stats (
                        cacheKey TEXT NOT NULL PRIMARY KEY,
                        today INTEGER NOT NULL,
                        upcoming INTEGER NOT NULL,
                        overdue INTEGER NOT NULL,
                        awaiting INTEGER NOT NULL,
                        red INTEGER NOT NULL,
                        updatedAtMillis INTEGER NOT NULL
                    )
                    """.trimIndent(),
                )
            }
        }

        private val MIGRATION_7_8 = object : Migration(7, 8) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS category_options (
                        id TEXT NOT NULL PRIMARY KEY,
                        payloadJson TEXT NOT NULL,
                        updatedAtMillis INTEGER NOT NULL
                    )
                    """.trimIndent(),
                )
            }
        }

        private val MIGRATION_8_9 = object : Migration(8, 9) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE notifications ADD COLUMN payloadJson TEXT NOT NULL DEFAULT '{}'")
            }
        }
    }
}
