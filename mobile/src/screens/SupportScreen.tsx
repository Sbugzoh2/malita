import React, { useCallback, useEffect, useState } from "react";
import {
  View,
  Text,
  TextInput,
  Pressable,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { useFocusEffect } from "@react-navigation/native";
import { useAuth } from "../context/AuthContext";
import { colors } from "../theme";
import {
  ApiError,
  SupportTicket,
  SupportTicketSummary,
  createMySupportTicket,
  fetchMySupportTickets,
  fetchMySupportTicket,
  replyToMySupportTicket,
} from "../api/client";

function formatDate(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString("en-ZA", {
    year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    timeZone: "Africa/Johannesburg",
  });
}

type View = "list" | "compose" | { ticketId: number };

export default function SupportScreen({ navigation }: any) {
  const { token } = useAuth();
  const [view, setView] = useState<View>("list");
  const [tickets, setTickets] = useState<SupportTicketSummary[] | null>(null);
  const [thread, setThread] = useState<SupportTicket | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [reply, setReply] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const loadList = useCallback(() => {
    if (!token) return;
    fetchMySupportTickets(token)
      .then((res) => setTickets(res.tickets))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load your support tickets."));
  }, [token]);

  useFocusEffect(
    useCallback(() => {
      if (view === "list") loadList();
    }, [view, loadList])
  );

  useEffect(() => {
    if (typeof view !== "object" || !token) return;
    setThread(null);
    fetchMySupportTicket(token, view.ticketId)
      .then(setThread)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load this ticket."));
  }, [view, token]);

  async function handleCreateTicket() {
    if (!token) return;
    if (!subject.trim() || !message.trim()) {
      setError("Please enter a subject and a message.");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const t = await createMySupportTicket(token, subject.trim(), message.trim());
      setSubject("");
      setMessage("");
      setView({ ticketId: t.id });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not send your message.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleReply() {
    if (!token || typeof view !== "object") return;
    if (!reply.trim()) return;
    setError(null);
    setSubmitting(true);
    try {
      const t = await replyToMySupportTicket(token, view.ticketId, reply.trim());
      setThread(t);
      setReply("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not send your reply.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
        <Pressable
          style={styles.backLink}
          onPress={() => (view === "list" ? navigation.goBack() : setView("list"))}
        >
          <Text style={styles.backLinkText}>‹ {view === "list" ? "Back" : "All tickets"}</Text>
        </Pressable>

        <Text style={styles.title}>Contact Support</Text>

        {error ? <Text style={styles.error}>{error}</Text> : null}

        {view === "list" ? (
          <>
            <Pressable style={styles.newButton} onPress={() => setView("compose")}>
              <Text style={styles.newButtonText}>+ New Message to Admin</Text>
            </Pressable>

            {!tickets ? (
              <ActivityIndicator color={colors.primary} style={{ marginTop: 24 }} />
            ) : tickets.length === 0 ? (
              <Text style={styles.empty}>No messages yet - tap "New Message to Admin" to get in touch.</Text>
            ) : (
              tickets.map((t) => (
                <Pressable key={t.id} style={styles.card} onPress={() => setView({ ticketId: t.id })}>
                  <View style={styles.cardHeaderRow}>
                    <Text style={styles.cardTitle}>{t.subject}</Text>
                    <View style={[styles.statusPill, t.status === "open" ? styles.statusOpen : styles.statusResolved]}>
                      <Text style={styles.statusPillText}>{t.status === "open" ? "Open" : "Resolved"}</Text>
                    </View>
                  </View>
                  <Text style={styles.cardMeta}>{formatDate(t.updated_at)}</Text>
                </Pressable>
              ))
            )}
          </>
        ) : view === "compose" ? (
          <View style={styles.card}>
            <Text style={styles.label}>Subject</Text>
            <TextInput style={styles.input} value={subject} onChangeText={setSubject} placeholder="e.g. Payment issue" />
            <Text style={styles.label}>Message</Text>
            <TextInput
              style={[styles.input, styles.textArea]}
              value={message}
              onChangeText={setMessage}
              placeholder="Tell us what's going on..."
              multiline
            />
            <Pressable style={styles.sendButton} onPress={handleCreateTicket} disabled={submitting}>
              {submitting ? <ActivityIndicator color="#fff" /> : <Text style={styles.sendButtonText}>Send</Text>}
            </Pressable>
          </View>
        ) : !thread ? (
          <ActivityIndicator color={colors.primary} style={{ marginTop: 24 }} />
        ) : (
          <>
            <Text style={styles.threadSubject}>{thread.subject}</Text>
            {thread.messages.map((m) => {
              const isAdmin = m.sender_kind === "admin";
              return (
                <View key={m.id} style={[styles.bubble, isAdmin ? styles.bubbleAdmin : styles.bubbleMine]}>
                  <Text style={isAdmin ? styles.bubbleSenderDark : styles.bubbleSender}>
                    {isAdmin ? "Malita Support" : "You"}
                  </Text>
                  <Text style={isAdmin ? styles.bubbleBodyDark : styles.bubbleBody}>{m.body}</Text>
                  <Text style={isAdmin ? styles.bubbleDateDark : styles.bubbleDate}>{formatDate(m.created_at)}</Text>
                </View>
              );
            })}

            {thread.status === "resolved" ? (
              <Text style={styles.resolvedNote}>This ticket has been marked resolved. You can still reply if you need to.</Text>
            ) : null}

            <TextInput
              style={[styles.input, styles.textArea, { marginTop: 16 }]}
              value={reply}
              onChangeText={setReply}
              placeholder="Write a reply..."
              multiline
            />
            <Pressable style={styles.sendButton} onPress={handleReply} disabled={submitting}>
              {submitting ? <ActivityIndicator color="#fff" /> : <Text style={styles.sendButtonText}>Reply</Text>}
            </Pressable>
          </>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.background },
  container: { padding: 20, paddingBottom: 48, flexGrow: 1 },
  backLink: { alignSelf: "flex-start", marginBottom: 12 },
  backLinkText: { color: colors.primary, fontWeight: "700", fontSize: 14 },
  title: { fontSize: 22, fontWeight: "800", color: colors.text, marginBottom: 16 },
  error: { color: colors.error, marginBottom: 12 },
  empty: { fontSize: 14, color: colors.textSecondary, marginTop: 20 },
  newButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 14,
    alignItems: "center",
    marginBottom: 20,
  },
  newButtonText: { color: "#fff", fontWeight: "700" },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 16,
    marginBottom: 12,
  },
  cardHeaderRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: 8 },
  cardTitle: { fontSize: 15, fontWeight: "700", color: colors.text, flex: 1 },
  cardMeta: { fontSize: 12, color: colors.textSecondary, marginTop: 8 },
  statusPill: { borderRadius: 999, paddingVertical: 4, paddingHorizontal: 10 },
  statusOpen: { backgroundColor: colors.primary },
  statusResolved: { backgroundColor: colors.success },
  statusPillText: { color: "#fff", fontSize: 11, fontWeight: "700" },
  label: { fontSize: 13, color: colors.textSecondary, marginBottom: 4, marginTop: 12 },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 15,
    color: colors.text,
    backgroundColor: "#fff",
  },
  textArea: { minHeight: 100, textAlignVertical: "top" },
  sendButton: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingVertical: 14,
    alignItems: "center",
    marginTop: 16,
  },
  sendButtonText: { color: "#fff", fontWeight: "700" },
  threadSubject: { fontSize: 17, fontWeight: "800", color: colors.text, marginBottom: 14 },
  bubble: { borderRadius: 16, padding: 14, marginBottom: 10, maxWidth: "90%" },
  bubbleMine: { backgroundColor: colors.surface, alignSelf: "flex-end" },
  bubbleAdmin: { backgroundColor: "#0b0b0b", alignSelf: "flex-start" },
  bubbleSender: { fontSize: 11, fontWeight: "700", color: colors.textSecondary, marginBottom: 4 },
  bubbleBody: { fontSize: 14, color: colors.text, lineHeight: 20 },
  bubbleDate: { fontSize: 11, color: colors.textSecondary, marginTop: 6 },
  // Dark-bubble variants (admin replies, "#0b0b0b" background) - same
  // light-on-dark palette as TutorHomeScreen's own dark stat cards
  // (#b9b8b3/#8a8984), not the default dark text which would be
  // unreadable against this background.
  bubbleSenderDark: { fontSize: 11, fontWeight: "700", color: "#b9b8b3", marginBottom: 4 },
  bubbleBodyDark: { fontSize: 14, color: "#fff", lineHeight: 20 },
  bubbleDateDark: { fontSize: 11, color: "#8a8984", marginTop: 6 },
  resolvedNote: { fontSize: 12, color: colors.textSecondary, marginTop: 8, fontStyle: "italic" },
});
