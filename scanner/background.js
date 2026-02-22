let response_id = '';
let authToken = '';

chrome.cookies.get(
  {
    url: 'https://hackeurope-zeta.vercel.app',
    name: 'sb-bjqtctmlonlqycbvymxs-auth-token.0'
  },
  (cookie0) => {
    if (!cookie0) {
      console.error('Cookie .0 not found');
      return;
    }

    chrome.cookies.get(
      {
        url: 'https://hackeurope-zeta.vercel.app',
        name: 'sb-bjqtctmlonlqycbvymxs-auth-token.1'
      },
      (cookie1) => {
        if (!cookie1) {
          console.error('Cookie .1 not found');
          return;
        }

        authToken = cookie0.value + cookie1.value;

        const decoded = atob(authToken.replace(/^base64-/, ''));
        const auth = JSON.parse(decoded);

        console.log(auth);
        console.log('JWT:', auth.access_token);
        authToken = auth.access_token;
      }
    );
  }
);

// console.log(authToken)
// const decoded = atob(authToken.replace(/^base64-/, ''));
// console.log(decoded)
// const auth = JSON.parse(decoded);
// console.log(auth)

chrome.runtime.onMessage.addListener((msg, sender) => {
  console.log("running background func")
  if (msg.type === 'FLIGHT_DATA') {
    fetch("https://bd1e6ddc7c2b.ngrok.app/api/analyze", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${authToken}`
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
        "Authorization": `Bearer ${authToken}`
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
              title: "Purchase warning",
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
        "Authorization": `Bearer ${authToken}`
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
