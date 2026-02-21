chrome.runtime.onMessage.addListener(async (msg) => {
  if (msg.type === 'FLIGHT_DATA') {
    console.log("sending post")
    fetch("https://bd1e6ddc7c2b.ngrok.app/api/analyze", {
      method: "POST",
      body: JSON.stringify(msg.payload),
      headers: {
        "Content-type": "application/json; charset=UTF-8",
        "Authorization": "Bearer eyJhbGciOiJFUzI1NiIsImtpZCI6ImI5YmY0NTBjLTViYmUtNDNlOS05MjVmLTRmNGZhMmE4MmViYyIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL2JqcXRjdG1sb25scXljYnZ5bXhzLnN1cGFiYXNlLmNvL2F1dGgvdjEiLCJzdWIiOiI0NjI0YWMyZC01NGVhLTQxYTItYjYzZS0yM2ExNzZiMDQ1NDciLCJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzcxNzA2NjExLCJpYXQiOjE3NzE3MDMwMTEsImVtYWlsIjoiY2FsbHVtQHRlc3QuY29tIiwicGhvbmUiOiIiLCJhcHBfbWV0YWRhdGEiOnsicHJvdmlkZXIiOiJlbWFpbCIsInByb3ZpZGVycyI6WyJlbWFpbCJdfSwidXNlcl9tZXRhZGF0YSI6eyJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwiZnVsbF9uYW1lIjoiQ2FsbHVtIn0sInJvbGUiOiJhdXRoZW50aWNhdGVkIiwiYWFsIjoiYWFsMSIsImFtciI6W3sibWV0aG9kIjoicGFzc3dvcmQiLCJ0aW1lc3RhbXAiOjE3NzE3MDMwMTF9XSwic2Vzc2lvbl9pZCI6ImZhMzBkM2M5LTVkMWUtNGE3NC05MDM5LTQ3OGUyNzMyYzI4YSIsImlzX2Fub255bW91cyI6ZmFsc2V9.9T9yWI93OP5QcO-hb3RxXnRsWO-FicUuYE7b6pqzzDEZNAxv0EP9oZTe5MeV3nZHueM8h5DrDGLsn4AsLozc9A"
      }
    })
    .then(res => res.json())
    .then(data => {
      console.log("API response:", data);

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
  }
});


// chrome.runtime.onMessage.addListener((msg, sender) => {
//   if (msg.type === 'FLIGHT_DATA') {
//     fetch("https://bd1e6ddc7c2b.ngrok.app/api/analyze", {
//       method: "POST",
//       headers: {
//         "Content-Type": "application/json",
//         "Authorization": "Bearer eyJhbGciOiJFUzI1NiIsImtpZCI6ImI5YmY0NTBjLTViYmUtNDNlOS05MjVmLTRmNGZhMmE4MmViYyIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL2JqcXRjdG1sb25scXljYnZ5bXhzLnN1cGFiYXNlLmNvL2F1dGgvdjEiLCJzdWIiOiI0NjI0YWMyZC01NGVhLTQxYTItYjYzZS0yM2ExNzZiMDQ1NDciLCJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzcxNzA2NjExLCJpYXQiOjE3NzE3MDMwMTEsImVtYWlsIjoiY2FsbHVtQHRlc3QuY29tIiwicGhvbmUiOiIiLCJhcHBfbWV0YWRhdGEiOnsicHJvdmlkZXIiOiJlbWFpbCIsInByb3ZpZGVycyI6WyJlbWFpbCJdfSwidXNlcl9tZXRhZGF0YSI6eyJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwiZnVsbF9uYW1lIjoiQ2FsbHVtIn0sInJvbGUiOiJhdXRoZW50aWNhdGVkIiwiYWFsIjoiYWFsMSIsImFtciI6W3sibWV0aG9kIjoicGFzc3dvcmQiLCJ0aW1lc3RhbXAiOjE3NzE3MDMwMTF9XSwic2Vzc2lvbl9pZCI6ImZhMzBkM2M5LTVkMWUtNGE3NC05MDM5LTQ3OGUyNzMyYzI4YSIsImlzX2Fub255bW91cyI6ZmFsc2V9.9T9yWI93OP5QcO-hb3RxXnRsWO-FicUuYE7b6pqzzDEZNAxv0EP9oZTe5MeV3nZHueM8h5DrDGLsn4AsLozc9A"
//       },
//       body: JSON.stringify(msg.payload)
//     })
//       .then(res => res.json())
//       .then(data => {
//         console.log("API response:", data);

//         if (data.is_safe === false && sender.tab?.id) {
//           chrome.tabs.sendMessage(sender.tab.id, {
//             type: "SHOW_MODAL",
//             payload: {
//               title: "Flight warning",
//               message: data.intervention_message || "This flight may not be safe."
//             }
//           });
//         }
//       })
//       .catch(err => {
//         console.error("Analyze API error:", err);
//       });

//     return true;
//   }
// });
