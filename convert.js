export default async function handler(req, res) {
  const { amount, from, to } = req.query;

  if (!amount || !from || !to) {
    return res.status(400).json({ error: 'Missing required parameters: amount, from, to' });
  }

  const numAmount = parseFloat(amount);
  if (isNaN(numAmount)) {
    return res.status(400).json({ error: 'Invalid amount' });
  }

  try {
    // Fetch exchange rates from exchangerate-api.com (free tier)
    const response = await fetch(`https://api.exchangerate-api.com/v4/latest/${from}`);
    const data = await response.json();

    if (!response.ok) {
      throw new Error('Failed to fetch exchange rates');
    }

    const rate = data.rates[to];
    if (!rate) {
      return res.status(400).json({ error: 'Invalid currency code' });
    }

    const result = (numAmount * rate).toFixed(2);
    res.status(200).json({ result });
  } catch (error) {
    res.status(500).json({ error: 'Internal server error' });
  }
}
