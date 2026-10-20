# SQLCipher
-keep class net.sqlcipher.** { *; }
-keep class net.sqlcipher.database.** { *; }

# Room génère des implémentations réfléchies au runtime pour les migrations.
-keep class * extends androidx.room.RoomDatabase { <init>(); }
