# yc_mcp_hackathon

requires freecad-mcp
https://github.com/neka-nat/freecad-mcp

**Overall Flow:**

*   The user's query and chat history are received.
*   **Step 1 (Design Calculation)**. The results are prepared for UI display.
*   **Step 2 (3D Modeling)**:
    *   If the modeling agent is not initialized, an attempt is made to initialize it. If initialization fails, this step is skipped, and an error message is recorded for the documentation.
    *   If successful (or already initialized), the modeling task is performed using the specifications from Step 1.
    *   The result (image or text) is prepared for UI display and recorded for the documentation step.
*   **Step 3 (Document Generation)** is executed using the original query, calculation specs, and a summary of the modeling result.
*   The function returns a list of messages to be displayed in the chat interface and the content of the generated Markdown proposal.
