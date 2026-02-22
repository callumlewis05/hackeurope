function scrapeSearchData(root = document) {
  const data = {};

  data.user_id = "";
  data.domain = "skyscanner.net";
  data.intent = {};

  data.intent.type = "flight_booking";
  data.intent.outbound = {};
  data.intent.return = {};

  const trip_details = root.querySelectorAll('[data-testid="leg-summary"]');
  const flightDates = document.querySelectorAll('h3[data-backpack-ds-component="Text"] span');
  const flightNumbers = document.querySelectorAll('.AirlineLogoTitle_container__MTE3Z span');

  const outboundText = trip_details[0].querySelectorAll('[data-backpack-ds-component="Text"]');
  console.log(outboundText);
  let returnText = [];
  if (trip_details.length > 1) {
    returnText = trip_details[1].querySelectorAll('[data-backpack-ds-component="Text"]')
  }

  const connecting_flight = outboundText.length > 11;

  data.intent.outbound.airline = outboundText[0].innerHTML.split(';')[1];
  data.intent.outbound.flight_number = flightNumbers[3].textContent;
  data.intent.outbound.departure_date = flightDates[0].textContent;
  data.intent.outbound.departure_time = outboundText[2 + connecting_flight].innerHTML;
  data.intent.outbound.departure_airport = outboundText[4 + connecting_flight].innerHTML;
  data.intent.outbound.arrival_time = outboundText[8 + connecting_flight].innerHTML;
  data.intent.outbound.arrival_airport = outboundText[10 + connecting_flight].innerHTML;
  data.intent.outbound.duration = outboundText[5 + connecting_flight].innerHTML + "m";
  data.intent.outbound.stops = outboundText[6 + connecting_flight].innerHTML;
  data.intent.outbound.self_transfer = !(outboundText[6 + connecting_flight].innerHTML === "Direct");

  data.intent.return.airline = returnText[0].innerHTML.split(';')[1];
  data.intent.return.flight_number = flightNumbers[7].textContent;
  data.intent.return.departure_date = flightDates[1].textContent;
  data.intent.return.departure_time = returnText[2 + connecting_flight].innerHTML;
  data.intent.return.departure_airport = returnText[4 + connecting_flight].innerHTML;
  data.intent.return.arrival_time = returnText[8 + connecting_flight].innerHTML;
  data.intent.return.arrival_airport = returnText[10 + connecting_flight].innerHTML;
  data.intent.return.duration = returnText[5 + connecting_flight].innerHTML + "m";
  data.intent.return.stops = returnText[6 + connecting_flight].innerHTML;
  data.intent.return.self_transfer = !(returnText[6 + connecting_flight].innerHTML === "Direct");

  console.log(data);

  return data;
}

function waitForElement(selector, callback) {
  const existing = document.querySelector(selector);
  if (existing) {
    callback(existing);
    return;
  }

  const observer = new MutationObserver(() => {
    const el = document.querySelector(selector);
    if (el) {
      observer.disconnect();
      callback(el);
    }
  });

  observer.observe(document.documentElement, {
    childList: true,
    subtree: true
  });
}

waitForElement('[data-testid="leg-summary"]', () => {
  chrome.runtime.sendMessage({ type: 'FLIGHT_DATA', payload: scrapeSearchData(document) });
});

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === 'SHOW_MODAL') {
    showModal(msg.payload);
  }
});

function sendFeedback(feedback) {
  console.log(`Sending ${feedback} feedback`);
  chrome.runtime.sendMessage({ type: 'FEEDBACK', payload: {"feedback": feedback} });
}

async function showModal({ title, message }) {
  if (document.getElementById("flight-alert-modal-overlay")) return;

  // Load modal HTML
  const htmlText = await fetch(chrome.runtime.getURL("notification/notification.html"))
    .then(res => res.text());

  const template = document.createElement("div");
  template.innerHTML = htmlText;

  const overlay = template.firstElementChild;
  document.body.appendChild(overlay);

  // Load CSS
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = chrome.runtime.getURL("notification/notification.css");
  document.head.appendChild(link);

  // Set content
  overlay.querySelector("#modal-title").textContent = title;
  overlay.querySelector("#modal-message").textContent = message;

  // Close button
  overlay.querySelector("#modal-close").onclick = () => overlay.remove();
  overlay.querySelector("#positive-feedback-button").onclick = () => {overlay.remove(); sendFeedback("positive")};
  overlay.querySelector("#negative-feedback-button").onclick = () => {overlay.remove(); sendFeedback("negative")};
}
