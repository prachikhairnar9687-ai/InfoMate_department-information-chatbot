const form = document.getElementById("chat-form");
const input = document.getElementById("question");
const messages = document.getElementById("messages");

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

function addDocumentLinks(bubble, documents) {
  if (!Array.isArray(documents) || documents.length === 0) {
    return;
  }

  const section = document.createElement("div");
  section.className = "chat-documents";

  const heading = document.createElement("p");
  heading.className = "chat-documents-heading";
  heading.textContent = "📚 Related department PDFs";
  section.appendChild(heading);

  documents.forEach((doc) => {
    if (!doc.id || !doc.name) return;

    const link = document.createElement("a");
    link.className = "chat-document-link";
    link.href =
      `/api/documents/${encodeURIComponent(doc.id)}/open`;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = `📄 View PDF: ${doc.name}`;
    link.title = `Open ${doc.name}`;

    section.appendChild(link);
  });

  if (section.children.length > 1) {
    bubble.appendChild(section);
  }

  messages.scrollTop = messages.scrollHeight;
}

async function ask(q) {
  if (!q.trim()) return;

  addMessage(q, "user");

  input.value = "";
  input.focus();

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

    const data = await response.json();

    if (!response.ok) {
      pending.textContent =
        data.answer || "I couldn't generate an answer. Please try again.";
      return;
    }

    pending.textContent =
      data.answer || "I couldn't generate an answer. Please try again.";

    addDocumentLinks(pending, data.documents || []);

  } catch (error) {
    pending.textContent =
      "I couldn't connect to InfoMate. Please check your internet connection and try again.";
  }
}

form?.addEventListener("submit", (event) => {
  event.preventDefault();
  ask(input.value);
});

document.querySelectorAll("[data-q]").forEach((button) => {
  button.addEventListener("click", () => ask(button.dataset.q));
});

document.getElementById("reset")?.addEventListener("click", () => {
  messages.innerHTML = "";

  addMessage(
    "Hey there! 😊 What would you like to know?\n\nChoose a suggestion below or type your question.",
    "bot"
  );
});