# Agentic Flow Architecture Design

**Status:** ⏳ Design Phase  
**Phase:** 17.1 - Agentic Flow Implementation  
**Last Updated:** 2025-11-19

## Overview

This document outlines the architecture for implementing agentic reasoning/planning before responding to users. The goal is to move beyond simple one-off LLM calls to a structured reasoning loop that improves response quality through planning, execution, and reflection.

## Current State

### Existing Agent Implementations

1. **Chat Agent Handler** (`essence/chat/agent/handler.py`):
   - Calls external scripts from "agenticness" directory
   - Simple request-response pattern
   - Supports streaming responses
   - Uses session management (user_id, chat_id)

2. **Coding Agent** (`essence/agents/coding_agent.py`):
   - Direct gRPC integration with LLM (TensorRT-LLM)
   - Tool calling interface (file operations, code execution)
   - Multi-turn conversation support
   - Sandboxed execution

### Limitations

- No structured reasoning loop
- No planning phase before execution
- No reflection/evaluation phase after execution
- Direct responses without intermediate reasoning steps
- Limited ability to break down complex tasks

## Proposed Architecture

### Reasoning Loop Structure

```
User Message
    ↓
[THINK] - Analyze request, determine complexity
    ↓
[PLAN] - Break down into steps, identify tools needed
    ↓
[EXECUTE] - Carry out plan step-by-step
    ↓
[REFLECT] - Evaluate results, adjust if needed
    ↓
[RESPOND] - Format and send final response
```

### Components

#### 1. Agentic Reasoning Service (`essence/agents/reasoning.py`)

**Purpose:** Core reasoning loop implementation

**Key Classes:**

```python
class AgenticReasoner:
    """Main reasoning orchestrator"""
    
    def reason(
        self,
        user_message: str,
        context: ConversationContext,
        max_iterations: int = 5
    ) -> ReasoningResult:
        """
        Execute reasoning loop:
        1. Think: Analyze request
        2. Plan: Create execution plan
        3. Execute: Carry out plan
        4. Reflect: Evaluate results
        5. Repeat if needed (up to max_iterations)
        """
        pass

class ReasoningState:
    """Tracks state through reasoning loop"""
    - current_step: str  # "think", "plan", "execute", "reflect"
    - plan: List[Step]
    - execution_results: List[ExecutionResult]
    - reflection: ReflectionResult
    - iteration: int
```

#### 2. Planning Component (`essence/agents/planner.py`)

**Purpose:** Break down user requests into executable steps

**Key Classes:**

```python
class Planner:
    """Creates execution plans from user requests"""
    
    def create_plan(
        self,
        user_request: str,
        available_tools: List[Tool],
        context: ConversationContext
    ) -> Plan:
        """
        Generate a step-by-step plan:
        - Identify required tools
        - Determine execution order
        - Estimate complexity
        - Set success criteria
        """
        pass

class Plan:
    """Represents an execution plan"""
    - steps: List[Step]
    - estimated_complexity: str  # "simple", "moderate", "complex"
    - success_criteria: List[str]
    - required_tools: List[str]
```

#### 3. Execution Component (`essence/agents/executor.py`)

**Purpose:** Execute planned steps using available tools

**Key Classes:**

```python
class Executor:
    """Executes planned steps"""
    
    def execute_step(
        self,
        step: Step,
        context: ExecutionContext
    ) -> ExecutionResult:
        """
        Execute a single step:
        - Call appropriate tool
        - Handle errors
        - Collect results
        """
        pass

class ExecutionResult:
    """Result of executing a step"""
    - success: bool
    - output: Any
    - error: Optional[str]
    - execution_time: float
    - tool_used: str
```

#### 4. Reflection Component (`essence/agents/reflector.py`)

**Purpose:** Evaluate execution results and adjust plan if needed

**Key Classes:**

```python
class Reflector:
    """Evaluates execution results"""
    
    def reflect(
        self,
        plan: Plan,
        execution_results: List[ExecutionResult],
        original_request: str
    ) -> ReflectionResult:
        """
        Evaluate:
        - Did we achieve the goal?
        - Are there errors to fix?
        - Should we adjust the plan?
        - Is the response complete?
        """
        pass

class ReflectionResult:
    """Result of reflection phase"""
    - goal_achieved: bool
    - issues_found: List[str]
    - plan_adjustments: Optional[Plan]
    - should_continue: bool
    - final_response: Optional[str]
```

### Decision Logic: When to Use Agentic Flow

#### Use Agentic Flow When:
- **Complex requests:** Multi-step tasks requiring planning
- **Tool usage needed:** Requests that require file operations, code execution, etc.
- **Ambiguous requests:** User intent unclear, needs reasoning
- **Explicit request:** User asks for "reasoning" or "step-by-step"
- **Previous failure:** Direct response failed, retry with reasoning

#### Use Direct Response When:
- **Simple questions:** Factual questions, simple explanations
- **Low complexity:** Single-step tasks
- **Performance critical:** Latency-sensitive requests
- **Explicit request:** User asks for "quick" or "direct" response

#### Decision Function:

```python
def should_use_agentic_flow(
    user_message: str,
    message_history: List[Message],
    available_tools: List[Tool]
) -> bool:
    """
    Determine if agentic flow should be used.
    
    Returns True if:
    - Message contains keywords: "plan", "step", "reason", "think"
    - Message length > threshold (complex requests)
    - Previous messages indicate complexity
    - Tools are available and likely needed
    """
    # Check for explicit keywords
    agentic_keywords = ["plan", "step", "reason", "think", "break down"]
    if any(keyword in user_message.lower() for keyword in agentic_keywords):
        return True
    
    # Check complexity indicators
    if len(user_message) > 200:  # Long messages often need planning
        return True
    
    # Check if tools are likely needed
    tool_keywords = ["file", "code", "write", "create", "modify", "execute"]
    if any(keyword in user_message.lower() for keyword in tool_keywords):
        return True
    
    # Check conversation history for complexity
    if len(message_history) > 3:  # Multi-turn conversations
        return True
    
    return False
```

### Conversation Context Management

#### Context Structure:

```python
class ConversationContext:
    """Manages conversation state"""
    - user_id: str
    - chat_id: str
    - message_history: List[Message]
    - reasoning_history: List[ReasoningSession]
    - tool_state: Dict[str, Any]  # State of tools (workspace, files, etc.)
    - preferences: UserPreferences  # User's preferences for reasoning depth
```

#### Context Storage:

- **In-memory:** For active conversations (fast access)
- **Session-based:** Per user/chat session
- **Persistence:** Optional persistence for long-running conversations
- **Cleanup:** Remove old contexts after timeout

### Integration Points

#### 1. Integration with Chat Agent Handler

**Location:** `essence/chat/agent/handler.py`

**Changes:**
- Add decision logic to choose agentic vs direct flow
- Route to `AgenticReasoner` for complex requests
- Maintain backward compatibility with existing flow

```python
def process_agent_message(...):
    # Decision logic
    if should_use_agentic_flow(user_message, message_history, available_tools):
        # Use agentic flow
        result = agentic_reasoner.reason(user_message, context)
        return format_agentic_response(result)
    else:
        # Use direct flow (existing implementation)
        return call_chat_response_agent(...)
```

#### 2. Integration with LLM (TensorRT-LLM)

**Location:** `essence/agents/coding_agent.py` (or new `essence/agents/llm_client.py`)

**Changes:**
- Reuse existing gRPC client infrastructure
- Add specialized prompts for reasoning phases
- Support structured outputs for planning/reflection

```python
class LLMClient:
    """Unified LLM client for all reasoning phases"""
    
    def think(self, user_message: str, context: str) -> str:
        """Generate thinking/analysis"""
        prompt = f"Analyze this request: {user_message}\n\nContext: {context}"
        return self.generate(prompt, temperature=0.3)
    
    def plan(self, analysis: str, available_tools: List[str]) -> Plan:
        """Generate execution plan"""
        prompt = f"Create a plan: {analysis}\n\nTools: {available_tools}"
        return self.generate_structured(prompt, Plan)
    
    def reflect(self, plan: Plan, results: List[ExecutionResult]) -> ReflectionResult:
        """Generate reflection/evaluation"""
        prompt = f"Evaluate: Plan={plan}, Results={results}"
        return self.generate_structured(prompt, ReflectionResult)
```

#### 3. Integration with Tool System

**Location:** `essence/agents/coding_agent.py` (existing tools)

**Changes:**
- Reuse existing tool calling infrastructure
- Add tool result tracking for reflection
- Support tool chaining (output of one tool as input to another)

### Performance Considerations

#### Latency Management:

1. **Timeout per phase:**
   - Think: 10 seconds max
   - Plan: 15 seconds max
   - Execute: Variable (per step)
   - Reflect: 10 seconds max
   - Total: 60 seconds max per iteration

2. **Iteration limits:**
   - Max 5 iterations per request
   - Early termination if goal achieved
   - Timeout if total time exceeds threshold

3. **Caching:**
   - Cache common reasoning patterns
   - Cache plan templates for similar requests
   - Cache reflection evaluations

4. **Parallelization:**
   - Execute independent steps in parallel
   - Batch tool calls where possible

### Error Handling

#### Error Recovery:

1. **Step failures:**
   - Retry with adjusted parameters
   - Fall back to alternative approach
   - Report error to reflection phase

2. **Plan failures:**
   - Regenerate plan with error context
   - Simplify plan if too complex
   - Fall back to direct response

3. **LLM failures:**
   - Retry with exponential backoff
   - Fall back to direct response
   - Report error to user

### Testing Strategy

#### Unit Tests:

- Test each component independently
- Mock LLM calls
- Test decision logic
- Test error handling

#### Integration Tests:

- Test full reasoning loop
- Test with real LLM (TensorRT-LLM)
- Test tool integration
- Test performance under load

#### End-to-End Tests:

- Test with real user scenarios
- Test latency and timeout handling
- Test error recovery
- Compare agentic vs direct responses

## Implementation Plan

### Phase 1: Core Infrastructure (Current Task)
- ✅ Design architecture (this document)
- ⏳ Implement `AgenticReasoner` class
- ⏳ Implement `ReasoningState` tracking
- ⏳ Add decision logic for agentic vs direct flow

### Phase 2: Planning Component
- ⏳ Implement `Planner` class
- ⏳ Create plan generation prompts
- ⏳ Test plan generation with various request types

### Phase 3: Execution Component
- ⏳ Implement `Executor` class
- ⏳ Integrate with existing tool system
- ⏳ Add error handling and retry logic

### Phase 4: Reflection Component
- ⏳ Implement `Reflector` class
- ⏳ Create reflection evaluation prompts
- ⏳ Test reflection with various outcomes

### Phase 5: Integration
- ⏳ Integrate with chat agent handler
- ⏳ Add conversation context management
- ⏳ Test end-to-end flow

### Phase 6: Optimization
- ⏳ Optimize latency
- ⏳ Add caching
- ⏳ Fine-tune decision logic
- ⏳ Performance testing

## Success Criteria

1. **Functionality:**
   - Agentic flow handles complex requests better than direct flow
   - Reasoning loop completes successfully for multi-step tasks
   - Reflection phase identifies and fixes errors

2. **Performance:**
   - Agentic flow latency < 2x direct flow latency
   - Timeout handling works correctly
   - No memory leaks or resource issues

3. **Quality:**
   - Agentic responses are more accurate/complete
   - Planning improves task success rate
   - Reflection catches and fixes errors

## Related Documentation

- `REFACTOR_PLAN.md` - Phase 17 tasks
- `docs/guides/AGENTS.md` - Agent development guidelines
- `essence/agents/coding_agent.py` - Existing coding agent implementation
- `essence/chat/agent/handler.py` - Current chat agent handler

## Notes

- This design maintains backward compatibility with existing agent implementations
- The decision logic can be tuned based on real-world usage patterns
- Performance optimizations can be added incrementally
- The architecture is extensible for future enhancements (e.g., multi-agent collaboration)
