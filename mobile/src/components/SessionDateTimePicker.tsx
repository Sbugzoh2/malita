import React, { useState } from "react";
import { View, Text, Pressable, Modal, StyleSheet } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors } from "../theme";
import Dropdown from "./Dropdown";

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
// Exported for reuse anywhere else that needs the same Hour/Minute pair
// (e.g. TutorApplyScreen's weekly availability picker).
export const HOUR_OPTIONS = Array.from({ length: 24 }, (_, i) => ({
  label: String(i).padStart(2, "0"), value: String(i),
}));
export const MINUTE_OPTIONS = ["00", "15", "30", "45"].map((m) => ({ label: m, value: m }));

export type SessionDateTimeValue = {
  year: number; month: number; day: number; hour: number; minute: number;
} | null;

function startOfDay(d: Date): Date {
  const r = new Date(d);
  r.setHours(0, 0, 0, 0);
  return r;
}

// South Africa is a fixed UTC+2 offset year-round (no daylight saving) -
// these convert explicitly rather than relying on the device's own
// timezone, so every learner/tutor is scheduling the same real-world
// instant regardless of what timezone their phone happens to be set to.
export function sessionDateTimeToIso(v: NonNullable<SessionDateTimeValue>): string {
  const utcMillis = Date.UTC(v.year, v.month, v.day, v.hour - 2, v.minute, 0);
  return new Date(utcMillis).toISOString();
}

export function isoToSessionDateTime(iso: string): NonNullable<SessionDateTimeValue> {
  const utcDate = new Date(iso);
  const sast = new Date(utcDate.getTime() + 2 * 60 * 60 * 1000);
  return {
    year: sast.getUTCFullYear(), month: sast.getUTCMonth(), day: sast.getUTCDate(),
    hour: sast.getUTCHours(), minute: sast.getUTCMinutes(),
  };
}

type Props = {
  label: string;
  value: SessionDateTimeValue;
  onChange: (v: NonNullable<SessionDateTimeValue>) => void;
  minDate?: Date;
};

// A pure JS/RN calendar + hour/minute picker - deliberately not
// @react-native-community/datetimepicker, which is a native module and
// would force a full rebuild; this ships via EAS Update like Dropdown.
export default function SessionDateTimePicker({ label, value, onChange, minDate }: Props) {
  const [open, setOpen] = useState(false);
  // Same fix as Dropdown.tsx - a flat paddingBottom sits flush with a
  // gesture-nav phone's home-indicator strip, so a tap near the bottom of
  // this sheet can register as the system's back/home swipe instead.
  const insets = useSafeAreaInsets();
  const floor = startOfDay(minDate ?? new Date());
  const initialBase = value ? new Date(value.year, value.month, value.day) : floor;
  const [viewMonth, setViewMonth] = useState(new Date(initialBase.getFullYear(), initialBase.getMonth(), 1));

  const year = viewMonth.getFullYear();
  const month = viewMonth.getMonth();
  const firstDayOfWeek = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells: (number | null)[] = [];
  for (let i = 0; i < firstDayOfWeek; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);

  function updateValue(partial: Partial<NonNullable<SessionDateTimeValue>>) {
    const base = value ?? { year: floor.getFullYear(), month: floor.getMonth(), day: floor.getDate(), hour: 9, minute: 0 };
    onChange({ ...base, ...partial });
  }

  const selectedDateLabel = value
    ? new Date(value.year, value.month, value.day).toLocaleDateString("en-ZA", {
        year: "numeric", month: "long", day: "numeric",
      })
    : "Select a date";

  return (
    <View>
      <Text style={styles.label}>{label}</Text>
      <Pressable style={styles.trigger} onPress={() => setOpen(true)}>
        <Text style={styles.triggerText}>{selectedDateLabel}</Text>
        <Text style={styles.chevron}>📅</Text>
      </Pressable>

      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <Pressable style={styles.backdrop} onPress={() => setOpen(false)}>
          <View
            style={[styles.sheet, { paddingBottom: 24 + insets.bottom }]}
            onStartShouldSetResponder={() => true}
          >
            <View style={styles.monthRow}>
              <Pressable onPress={() => setViewMonth(new Date(year, month - 1, 1))} style={styles.monthNavBtn}>
                <Text style={styles.monthNav}>‹</Text>
              </Pressable>
              <Text style={styles.monthLabel}>{MONTH_NAMES[month]} {year}</Text>
              <Pressable onPress={() => setViewMonth(new Date(year, month + 1, 1))} style={styles.monthNavBtn}>
                <Text style={styles.monthNav}>›</Text>
              </Pressable>
            </View>
            <View style={styles.weekRow}>
              {WEEKDAY_LABELS.map((w) => (
                <Text key={w} style={styles.weekdayLabel}>{w}</Text>
              ))}
            </View>
            <View style={styles.grid}>
              {cells.map((day, i) => {
                if (day === null) return <View key={i} style={styles.dayCell} />;
                const cellDate = new Date(year, month, day);
                const disabled = cellDate < floor;
                const isSelected = !!value && value.year === year && value.month === month && value.day === day;
                return (
                  <Pressable
                    key={i}
                    style={[styles.dayCell, isSelected && styles.dayCellSelected]}
                    onPress={() => {
                      if (disabled) return;
                      updateValue({ year, month, day });
                      setOpen(false);
                    }}
                    disabled={disabled}
                  >
                    <Text
                      style={[
                        styles.dayText,
                        disabled && styles.dayTextDisabled,
                        isSelected && styles.dayTextSelected,
                      ]}
                    >
                      {day}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
          </View>
        </Pressable>
      </Modal>

      <View style={styles.timeRow}>
        <View style={styles.timeCol}>
          <Dropdown
            label="Hour (SAST)"
            options={HOUR_OPTIONS}
            value={value ? String(value.hour) : null}
            onChange={(v) => updateValue({ hour: parseInt(v, 10) })}
          />
        </View>
        <View style={styles.timeCol}>
          <Dropdown
            label="Minute"
            options={MINUTE_OPTIONS}
            value={value ? String(value.minute).padStart(2, "0") : null}
            onChange={(v) => updateValue({ minute: parseInt(v, 10) })}
          />
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  label: { fontSize: 13, fontWeight: "600", color: colors.textSecondary, marginTop: 14, marginBottom: 6 },
  trigger: {
    flexDirection: "row",
    alignItems: "center",
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    paddingVertical: 12,
    paddingHorizontal: 14,
    backgroundColor: "#fff",
  },
  triggerText: { flex: 1, fontSize: 15, color: colors.text },
  chevron: { fontSize: 16, marginLeft: 8 },
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.4)",
    justifyContent: "flex-end",
  },
  sheet: {
    backgroundColor: "#fff",
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    paddingTop: 16,
    paddingBottom: 24,
    paddingHorizontal: 16,
  },
  monthRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 12 },
  monthNavBtn: { paddingHorizontal: 16, paddingVertical: 4 },
  monthNav: { fontSize: 22, color: colors.primary, fontWeight: "700" },
  monthLabel: { fontSize: 16, fontWeight: "700", color: colors.text },
  weekRow: { flexDirection: "row" },
  weekdayLabel: {
    width: `${100 / 7}%`,
    textAlign: "center",
    fontSize: 12,
    fontWeight: "600",
    color: colors.textSecondary,
    marginBottom: 6,
  },
  grid: { flexDirection: "row", flexWrap: "wrap" },
  dayCell: {
    width: `${100 / 7}%`,
    aspectRatio: 1,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 999,
  },
  dayCellSelected: { backgroundColor: colors.primary },
  dayText: { fontSize: 14, color: colors.text },
  dayTextDisabled: { color: colors.border },
  dayTextSelected: { color: "#fff", fontWeight: "700" },
  timeRow: { flexDirection: "row", gap: 12 },
  timeCol: { flex: 1 },
});
