const form = document.getElementById("chat-form");
const input = document.getElementById("question");
const messages = document.getElementById("messages");
const resetButton = document.getElementById("reset");

const WELCOME_MESSAGE =
  "Hey there! 😊 What would you like to know?\n\n" +
  "Choose a suggestion below or type your question.";

let requestInProgress = false;

function addMessage(text, who) {
  const row = document.createElement("div");
  row.className = `message-row ${who}`;

  const avatar = document.createElement("span");
  avatar.className = "avatar";
  avatar.textContent = who === "bot" ? "✦" : "You";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;

  row.append(avatar, bubble);
  messages.appendChild(row);
  messages.scrollTop = messages.scrollHeight;

  return bubble;
}

function initializeChat() {
  if (!messages) return;

  messages.innerHTML = "";
  addMessage(WELCOME_MESSAGE, "bot");
}

function addDocumentLinks(bubble, documents) {
  if (!Array.isArray(documents) || documents.length === 0) {
    return;
  }

  const section = document.createElement("div");
  section.className = "chat-documents";

  const heading = document.createElement("p");
  heading.className = "chat-documents-heading";
  heading.textContent = "📚 Related department documents";
  section.appendChild(heading);

  documents.forEach((doc) => {
    if (!doc || !doc.id || !doc.name) return;

    const link = document.createElement("a");
    link.className = "chat-document-link";
    link.href = `/api/documents/${encodeURIComponent(doc.id)}/open`;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = `📄 Open: ${doc.name}`;
    link.title = `Open ${doc.name}`;

    section.appendChild(link);
  });

  if (section.children.length > 1) {
    bubble.appendChild(section);
  }

  messages.scrollTop = messages.scrollHeight;
}

async function ask(question) {
  const q = String(question || "").trim();

  if (!q || requestInProgress || !messages) {
    return;
  }

  requestInProgress = true;

  const submitButton = form?.querySelector('button[type="submit"]');
  if (submitButton) submitButton.disabled = true;

  addMessage(q, "user");
  input.value = "";

  const pending = addMessage(
    "Checking approved department sources…",
    "bot"
  );

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ message: q })
    });

    let data;
    try {
      data = await response.json();
    } catch {
      data = {};
    }

    if (!response.ok) {
      pending.textContent =
        data.answer || "I couldn't generate an answer. Please try again.";
      return;
    }

    pending.textContent =
      data.answer || "I couldn't generate an answer. Please try again.";

    // The backend returns documents only when the user requested a file.
    addDocumentLinks(pending, data.documents || []);
  } catch (error) {
    console.error("InfoMate chat error:", error);
    pending.textContent =
      "I couldn't connect to InfoMate. Please check your connection and try again.";
  } finally {
    requestInProgress = false;
    if (submitButton) submitButton.disabled = false;
    input?.focus();
  }
}

form?.addEventListener("submit", (event) => {
  event.preventDefault();
  ask(input?.value);
});

document.querySelectorAll("[data-q]").forEach((button) => {
  button.addEventListener("click", () => {
    ask(button.dataset.q || "");
  });
});

resetButton?.addEventListener("click", initializeChat);

// Show the welcome message only when the chat area is initially empty.
if (messages && messages.children.length === 0) {
  initializeChat();
}
