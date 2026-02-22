function sendFeedback(feedback) {
    chrome.runtime.sendMessage({ type: 'FEEDBACK', payload: {"feedback": feedback} });
}
