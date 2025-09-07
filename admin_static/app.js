document.addEventListener('DOMContentLoaded', () => {
    const dataSections = document.getElementById('data-sections');
    const jsonOutput = document.getElementById('json-output');

    if (dataSections && jsonOutput) {
        dataSections.addEventListener('click', async (event) => {
            event.preventDefault();
            const target = event.target;

            if (target.tagName === 'A' && target.dataset.api) {
                const apiEndpoint = target.dataset.api;
                try {
                    // Assuming the backend is hosted on the same domain for admin access
                    // If not, you'd need to specify the full URL: e.g., `https://your-backend.onrender.com${apiEndpoint}`
                    const response = await fetch(apiEndpoint);
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    const data = await response.json();
                    jsonOutput.textContent = JSON.stringify(data, null, 2);
                } catch (error) {
                    jsonOutput.textContent = `Error fetching data: ${error.message}`;
                    console.error("Error fetching data:", error);
                }
            }
        });
    }
});
