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
  let returnText = [];
  if (trip_details.length > 1) {
    returnText = trip_details[1].querySelectorAll('[data-backpack-ds-component="Text"]')
  }

  data.intent.outbound.airline = outboundText[0].innerHTML.split(';')[1];
  data.intent.outbound.flight_number = flightNumbers[3].textContent;
  data.intent.outbound.departure_date = flightDates[0].textContent;
  data.intent.outbound.departure_time = outboundText[2].innerHTML;
  data.intent.outbound.departure_airport = outboundText[4].innerHTML;
  data.intent.outbound.arrival_time = outboundText[8].innerHTML;
  data.intent.outbound.arrival_airport = outboundText[10].innerHTML;
  data.intent.outbound.duration = outboundText[5].innerHTML + "m";
  data.intent.outbound.stops = outboundText[6].innerHTML;
  data.intent.outbound.self_transfer = (
    outboundText[6].innerHTML === "Direct" 
    ? false : outboundText[10]
  );

  data.intent.return.airline = returnText[0].innerHTML.split(';')[1];
  data.intent.return.flight_number = flightNumbers[7].textContent;
  data.intent.return.departure_date = flightDates[1].textContent;
  data.intent.return.departure_time = returnText[2].innerHTML;
  data.intent.return.departure_airport = returnText[4].innerHTML;
  data.intent.return.arrival_time = returnText[8].innerHTML;
  data.intent.return.arrival_airport = returnText[10].innerHTML;
  data.intent.return.duration = returnText[5].innerHTML + "m";
  data.intent.return.stops = returnText[6].innerHTML;
  data.intent.return.self_transfer = (
    returnText[6].innerHTML === "Direct" 
    ? false : returnText[10]
  );

  console.log(data);
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
  scrapeSearchData(document);
});
