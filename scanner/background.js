let response_id = '';

// chrome.cookies.get(
//   {
//     url: 'https://example.com',
//     name: 'hackeurope_access_token'
//   },
//   (cookie) => {
//     if (cookie) {
//       console.log(cookie.value);
//     } else {
//       console.log('Cookie not found');
//     }
//   }
// );

chrome.runtime.onMessage.addListener((msg, sender) => {
  console.log("running background func")
  if (msg.type === 'FLIGHT_DATA') {
    fetch("https://bd1e6ddc7c2b.ngrok.app/api/analyze", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        // "Authorization": `Bearer ${cookie.value}`
        "Authorization": `Bearer eyJhbGciOiJFUzI1NiIsImtpZCI6ImI5YmY0NTBjLTViYmUtNDNlOS05MjVmLTRmNGZhMmE4MmViYyIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL2JqcXRjdG1sb25scXljYnZ5bXhzLnN1cGFiYXNlLmNvL2F1dGgvdjEiLCJzdWIiOiI0NjI0YWMyZC01NGVhLTQxYTItYjYzZS0yM2ExNzZiMDQ1NDciLCJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzcxOTk5Mzk2LCJpYXQiOjE3NzE3NDAxOTYsImVtYWlsIjoiY2FsbHVtQHRlc3QuY29tIiwicGhvbmUiOiIiLCJhcHBfbWV0YWRhdGEiOnsicHJvdmlkZXIiOiJlbWFpbCIsInByb3ZpZGVycyI6WyJlbWFpbCJdfSwidXNlcl9tZXRhZGF0YSI6eyJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwiZnVsbF9uYW1lIjoiQ2FsbHVtIn0sInJvbGUiOiJhdXRoZW50aWNhdGVkIiwiYWFsIjoiYWFsMSIsImFtciI6W3sibWV0aG9kIjoicGFzc3dvcmQiLCJ0aW1lc3RhbXAiOjE3NzE3NDAxOTZ9XSwic2Vzc2lvbl9pZCI6ImMwNDQyNjk5LWRjNjUtNDA4Zi05NzY4LTgyYjAxY2NkNmRjNyIsImlzX2Fub255bW91cyI6ZmFsc2V9.NQmrz2k2oAcTp365G-UAsrUBqQzHr6nk2JsXOUjUlVVeVAc2iHN_h4iVbehHR0_imqyAkTs07kN7l_3HkxcbXA`
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

  if (msg.type === 'AMAZON_DATA') {
    fetch("https://bd1e6ddc7c2b.ngrok.app/api/analyze", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        // "Authorization": `Bearer ${cookie.value}`
        "Authorization": `Bearer eyJhbGciOiJFUzI1NiIsImtpZCI6ImI5YmY0NTBjLTViYmUtNDNlOS05MjVmLTRmNGZhMmE4MmViYyIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL2JqcXRjdG1sb25scXljYnZ5bXhzLnN1cGFiYXNlLmNvL2F1dGgvdjEiLCJzdWIiOiI0NjI0YWMyZC01NGVhLTQxYTItYjYzZS0yM2ExNzZiMDQ1NDciLCJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzcxOTk5Mzk2LCJpYXQiOjE3NzE3NDAxOTYsImVtYWlsIjoiY2FsbHVtQHRlc3QuY29tIiwicGhvbmUiOiIiLCJhcHBfbWV0YWRhdGEiOnsicHJvdmlkZXIiOiJlbWFpbCIsInByb3ZpZGVycyI6WyJlbWFpbCJdfSwidXNlcl9tZXRhZGF0YSI6eyJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwiZnVsbF9uYW1lIjoiQ2FsbHVtIn0sInJvbGUiOiJhdXRoZW50aWNhdGVkIiwiYWFsIjoiYWFsMSIsImFtciI6W3sibWV0aG9kIjoicGFzc3dvcmQiLCJ0aW1lc3RhbXAiOjE3NzE3NDAxOTZ9XSwic2Vzc2lvbl9pZCI6ImMwNDQyNjk5LWRjNjUtNDA4Zi05NzY4LTgyYjAxY2NkNmRjNyIsImlzX2Fub255bW91cyI6ZmFsc2V9.NQmrz2k2oAcTp365G-UAsrUBqQzHr6nk2JsXOUjUlVVeVAc2iHN_h4iVbehHR0_imqyAkTs07kN7l_3HkxcbXA`
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
              message: data.intervention_message || "This purchase may need a closer look."
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
    fetch(`https://bd1e6ddc7c2b.ngrok.app/api/interventions/${response_id}/feedback`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        // "Authorization": `Bearer ${cookie.value}`
        "Authorization": `Bearer eyJhbGciOiJFUzI1NiIsImtpZCI6ImI5YmY0NTBjLTViYmUtNDNlOS05MjVmLTRmNGZhMmE4MmViYyIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL2JqcXRjdG1sb25scXljYnZ5bXhzLnN1cGFiYXNlLmNvL2F1dGgvdjEiLCJzdWIiOiI0NjI0YWMyZC01NGVhLTQxYTItYjYzZS0yM2ExNzZiMDQ1NDciLCJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzcxOTk5Mzk2LCJpYXQiOjE3NzE3NDAxOTYsImVtYWlsIjoiY2FsbHVtQHRlc3QuY29tIiwicGhvbmUiOiIiLCJhcHBfbWV0YWRhdGEiOnsicHJvdmlkZXIiOiJlbWFpbCIsInByb3ZpZGVycyI6WyJlbWFpbCJdfSwidXNlcl9tZXRhZGF0YSI6eyJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwiZnVsbF9uYW1lIjoiQ2FsbHVtIn0sInJvbGUiOiJhdXRoZW50aWNhdGVkIiwiYWFsIjoiYWFsMSIsImFtciI6W3sibWV0aG9kIjoicGFzc3dvcmQiLCJ0aW1lc3RhbXAiOjE3NzE3NDAxOTZ9XSwic2Vzc2lvbl9pZCI6ImMwNDQyNjk5LWRjNjUtNDA4Zi05NzY4LTgyYjAxY2NkNmRjNyIsImlzX2Fub255bW91cyI6ZmFsc2V9.NQmrz2k2oAcTp365G-UAsrUBqQzHr6nk2JsXOUjUlVVeVAc2iHN_h4iVbehHR0_imqyAkTs07kN7l_3HkxcbXA`
      },
      body: JSON.stringify(msg.payload)
    })
      .then(response => {
        console.log("API response:", response.status);
      })
      .catch(err => {
        console.error("Feedback API error:", err);
      });

    return true;
  }
});
