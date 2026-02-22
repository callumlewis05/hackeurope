## What it does
Our project scans the websites you visit while booking flights and compares the dates you are looking at travelling with the current plans outlined in your calendar and emails. If it then detects a clash it will then offer a reminder/warning to ensure that it is not a mistake. The model is then trained off user feedback to ensure more accurate warnings in the future.

## Inspiration
Our inspiration came when discussing our upcoming and recent travel bookings. Sara, Arpan and Daglas all mentioned losing money due to booking errors. Sara mistakenly booked a train home on the 24th from London to Manchester, despite having booked an event in London taking place on the 28th, Arpan booked a PM flight, when he meant to book an AM flight and Daglas almost booked a flight the wrong way.

We thought this was a problem most people have encountered at least once and had a surprisingly elegant solution.

## How we built it
We used a combination of a chrome extension and a full stack web app to detect the current purchase interest and track and display the savings respectively.

## Challenges we ran into
Scraping website data is hard, especially as more websites use frameworks and generate obtuse and complex HTML so the detection is currently available on two sites.

## Accomplishments that we're proud of
Sleek dashboard, smooth popups and a product with real world potential to help save people money.

## What's next for Double Checker
Offer integration with more services such as social media and provide detection for more websites.
