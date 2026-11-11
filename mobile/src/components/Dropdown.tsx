import React, { useState } from "react";
import { View, Text, Pressable, Modal, FlatList, StyleSheet } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors } from "../theme";

export type DropdownOption = { label: string; value: string; color?: string; muted?: boolean };

type Props = {
  label: string;
  options: DropdownOption[];
  value: string | null;
  onChange: (value: string) => void;
};

// A simple, dependency-free dropdown (Pressable + Modal + FlatList) rather
// than pulling in @react-native-picker/picker - that's a native module and
// would force a full rebuild; this is pure JS/TS so it ships via EAS Update.
export default function Dropdown({ label, options, value, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const selected = options.find((o) => o.value === value);
  // Without this, a flat paddingBottom sits flush with a gesture-nav
  // phone's home-indicator strip - a tap meant for the last option (or
  // the sheet itself, on some devices) can register as the system's
  // back/home swipe instead, closing the app rather than picking an
  // option (reported by a tester on the Institution/Qualification
  // pickers specifically, but this affects every Dropdown instance).
  const insets = useSafeAreaInsets();

  return (
    <View>
      <Text style={styles.label}>{label}</Text>
      <Pressable style={styles.trigger} onPress={() => setOpen(true)}>
        {selected?.color ? <View style={[styles.swatch, { backgroundColor: selected.color }]} /> : null}
        <Text style={styles.triggerText} numberOfLines={1}>
          {selected?.label ?? "Select…"}
        </Text>
        <Text style={styles.chevron}>▾</Text>
      </Pressable>

      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <Pressable style={styles.backdrop} onPress={() => setOpen(false)}>
          <View
            style={[styles.sheet, { paddingBottom: 24 + insets.bottom }]}
            onStartShouldSetResponder={() => true}
          >
            <Text style={styles.sheetTitle}>{label}</Text>
            <FlatList
              data={options}
              keyExtractor={(o) => o.value}
              renderItem={({ item }) => (
                <Pressable
                  style={[styles.option, item.muted && styles.optionMuted]}
                  onPress={() => {
                    onChange(item.value);
                    setOpen(false);
                  }}
                >
                  {item.color ? <View style={[styles.swatch, { backgroundColor: item.color }]} /> : null}
                  <Text
                    style={[
                      styles.optionText,
                      item.value === value && { color: item.color ?? colors.primary, fontWeight: "700" },
                    ]}
                  >
                    {item.label}
                  </Text>
                  {item.value === value ? <Text style={styles.check}>✓</Text> : null}
                </Pressable>
              )}
            />
          </View>
        </Pressable>
      </Modal>
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
  chevron: { fontSize: 14, color: colors.textSecondary, marginLeft: 8 },
  swatch: { width: 12, height: 12, borderRadius: 6, marginRight: 10 },
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
    maxHeight: "70%",
  },
  sheetTitle: {
    fontSize: 16,
    fontWeight: "700",
    color: colors.text,
    paddingHorizontal: 20,
    marginBottom: 8,
  },
  option: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 14,
    paddingHorizontal: 20,
  },
  optionMuted: { opacity: 0.6 },
  optionText: { flex: 1, fontSize: 15, color: colors.text },
  check: { fontSize: 15, color: colors.primary, fontWeight: "700" },
});
