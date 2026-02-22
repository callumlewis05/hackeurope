let response_id = '';

chrome.cookies.get(
  {
    url: 'https://example.com', // must match cookie domain
    name: 'hackeurope_access_token'
  },
  (cookie) => {
    if (cookie) {
      console.log(cookie.value);
    } else {
      console.log('Cookie not found');
    }
  }
);

chrome.runtime.onMessage.addListener((msg, sender) => {
  if (msg.type === 'FLIGHT_DATA') {
    fetch("https://bd1e6ddc7c2b.ngrok.app/api/analyze", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${cookie.value}`
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
    fetch(`https://bd1e6ddc7c2b.ngrok.app/api/interventions/${response_id}/feedback`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${cookie.value}`
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
