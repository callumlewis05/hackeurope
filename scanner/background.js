let response_id = '';

chrome.runtime.onMessage.addListener((msg, sender) => {
  if (msg.type === 'FLIGHT_DATA') {
    fetch("https://bd1e6ddc7c2b.ngrok.app/api/analyze", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer eyJhbGciOiJFUzI1NiIsImtpZCI6ImI5YmY0NTBjLTViYmUtNDNlOS05MjVmLTRmNGZhMmE4MmViYyIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL2JqcXRjdG1sb25scXljYnZ5bXhzLnN1cGFiYXNlLmNvL2F1dGgvdjEiLCJzdWIiOiI0NjI0YWMyZC01NGVhLTQxYTItYjYzZS0yM2ExNzZiMDQ1NDciLCJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzcxOTcxODc5LCJpYXQiOjE3NzE3MTI2NzksImVtYWlsIjoiY2FsbHVtQHRlc3QuY29tIiwicGhvbmUiOiIiLCJhcHBfbWV0YWRhdGEiOnsicHJvdmlkZXIiOiJlbWFpbCIsInByb3ZpZGVycyI6WyJlbWFpbCJdfSwidXNlcl9tZXRhZGF0YSI6eyJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwiZnVsbF9uYW1lIjoiQ2FsbHVtIn0sInJvbGUiOiJhdXRoZW50aWNhdGVkIiwiYWFsIjoiYWFsMSIsImFtciI6W3sibWV0aG9kIjoicGFzc3dvcmQiLCJ0aW1lc3RhbXAiOjE3NzE3MTI2Nzl9XSwic2Vzc2lvbl9pZCI6IjExZmU3YWNmLWQ2MTEtNGJmNy04OWU3LTc4NzA1OGU5MjQ0ZSIsImlzX2Fub255bW91cyI6ZmFsc2V9.o0uhoqFyZPT4o1cWBvb9WndM-j_fjUsMJgVpr8GrAlwGXMLkPdonvyGepWhg0F4__ViGrIQ-Xn679cWCZGDqOg"
      },
      body: JSON.stringify(msg.payload)
    })
      .then(res => res.json())
      .then(data => {
        console.log("API response:", data);

        response_id = data.id;

        if (data.is_safe === false && sender.tab?.id) {
          chrome.tabs.sendMessage(sender.tab.id, {
            type: "SHOW_MODAL",
            payload: {
              title: "Flight warning",
              message: data.intervention_message || "This flight may not be safe."
            }
          });
        }
      })
      .catch(err => {
        console.error("Analyze API error:", err);
      });

    return true;
  }

  if (msg.type === 'FEEDBACK') {
    msg.payload.id = response_id;

    fetch("https://bd1e6ddc7c2b.ngrok.app/api/feedback", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer eyJhbGciOiJFUzI1NiIsImtpZCI6ImI5YmY0NTBjLTViYmUtNDNlOS05MjVmLTRmNGZhMmE4MmViYyIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL2JqcXRjdG1sb25scXljYnZ5bXhzLnN1cGFiYXNlLmNvL2F1dGgvdjEiLCJzdWIiOiI0NjI0YWMyZC01NGVhLTQxYTItYjYzZS0yM2ExNzZiMDQ1NDciLCJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzcxOTcxODc5LCJpYXQiOjE3NzE3MTI2NzksImVtYWlsIjoiY2FsbHVtQHRlc3QuY29tIiwicGhvbmUiOiIiLCJhcHBfbWV0YWRhdGEiOnsicHJvdmlkZXIiOiJlbWFpbCIsInByb3ZpZGVycyI6WyJlbWFpbCJdfSwidXNlcl9tZXRhZGF0YSI6eyJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwiZnVsbF9uYW1lIjoiQ2FsbHVtIn0sInJvbGUiOiJhdXRoZW50aWNhdGVkIiwiYWFsIjoiYWFsMSIsImFtciI6W3sibWV0aG9kIjoicGFzc3dvcmQiLCJ0aW1lc3RhbXAiOjE3NzE3MTI2Nzl9XSwic2Vzc2lvbl9pZCI6IjExZmU3YWNmLWQ2MTEtNGJmNy04OWU3LTc4NzA1OGU5MjQ0ZSIsImlzX2Fub255bW91cyI6ZmFsc2V9.o0uhoqFyZPT4o1cWBvb9WndM-j_fjUsMJgVpr8GrAlwGXMLkPdonvyGepWhg0F4__ViGrIQ-Xn679cWCZGDqOg"
      },
      body: JSON.stringify(msg.payload)
    })
      .then(res => res.json())
      .then(data => {
        console.log("API response:", data);
      })
      .catch(err => {
        console.error("Feedback API error:", err);
      });

    return true;
  }
});
