## Core Concepts and Dependencies

Here is the structured list of core linear algebra topics with prerequisite annotations:

1. **Scalar and Vector Arithmetic** (Addition, Scalar Multiplication)  
   - Prerequisites: None (Foundational)

2. **Dot Product and Norms**  
   - Prerequisites: Scalar and Vector Arithmetic

3. **Matrix Definition and Notation**  
   - Prerequisites: Scalar and Vector Arithmetic (specifically understanding columns/rows)

4. **Matrix Addition and Scalar Multiplication**  
   - Prerequisites: Matrix Definition and Notation, Vector Arithmetic

5. **Matrix-Vector Multiplication**  
   - Prerequisites: Dot Product and Norms, Matrix Definition

6. **Matrix-Matrix Multiplication**  
   - Prerequisites: Matrix-Vector Multiplication, Dot Product

7. **Systems of Linear Equations and Augmented Matrices**  
   - Prerequisites: Matrix Definition, Matrix-Vector Multiplication (conceptually related)

8. **Gaussian Elimination and Row Reduction**  
   - Prerequisites: Systems of Linear Equations and Augmented Matrices

9. **Rank and Null Space**  
   - Prerequisites: Gaussian Elimination and Row Reduction, Matrix-Vector Multiplication

10. **Determinants**  
    - Prerequisites: Matrix-Matrix Multiplication (for cofactor expansion intuition), Systems of Linear Equations

11. **Matrix Inversion**  
    - Prerequisites: Determinants, Gaussian Elimination, Matrix-Matrix Multiplication

12. **Vector Spaces and Subspaces**  
    - Prerequisites: Vector Arithmetic, Systems of Linear Equations, Null Space

13. **Linear Independence and Span**  
    - Prerequisites: Vector Spaces and Subspaces, Vector Arithmetic

14. **Basis and Dimension**  
    - Prerequisites: Linear Independence and Span, Rank

15. **Orthogonality and Projection**  
    - Prerequisites: Dot Product and Norms, Vector Spaces

16. **Eigenvalues and Eigenvectors**  
    - Prerequisites: Matrix Inversion, Determinants, Matrix-Vector Multiplication

17. **Diagonalization**  
    - Prerequisites: Eigenvalues and Eigenvectors, Matrix Inversion

## 7-Day Curriculum Outline

### 7-Day Linear Algebra Study Schedule

This schedule progresses from foundational arithmetic to solving systems of equations and analyzing matrix properties. It strictly follows the prerequisite dependencies identified in the core concepts list.

| Day | Focus Area | Specific Topics & Sub-Topics | Learning Objectives |
| :--- | :--- | :--- | :--- |
| **1** | **Foundations of Vectors and Matrices** | 1. Scalar and Vector Arithmetic (Addition, Scalar Multiplication)<br>2. Matrix Definition and Notation (Rows, Columns, Dimensions) | • Perform vector addition and scalar multiplication.<br>• Identify matrix dimensions and specific entries.<br>• Understand that matrices are collections of vectors (columns/rows). |
| **2** | **Vector Metrics & Basic Matrix Ops** | 1. Dot Product and Norms (Euclidean norm, orthogonality)<br>2. Matrix Addition and Scalar Multiplication | • Calculate dot products and vector norms.<br>• Add matrices and multiply by scalars.<br>• Understand geometric interpretations of dot product. |
| **3** | **Matrix Multiplication** | 1. Matrix-Vector Multiplication (Linear combination of columns)<br>2. Matrix-Matrix Multiplication (Composition of linear maps) | • Compute $A\mathbf{x}$ and $AB$.<br>• Understand matrix multiplication as a series of dot products.<br>• Recognize non-commutativity ($AB \neq BA$). |
| **4** | **Systems of Linear Equations** | 1. Systems of Linear Equations and Augmented Matrices<br>2. Consistency and Geometric Interpretation | • Translate systems into matrix form $A\mathbf{x} = \mathbf{b}$.<br>• Construct and interpret augmented matrices.<br>• Visualize solutions as intersecting lines/planes. |
| **5** | **Solving Systems via Elimination** | 1. Gaussian Elimination<br>2. Row Reduction (REF and RREF) | • Apply elementary row operations.<br>• Reduce matrices to Row Echelon Form (REF) and Reduced Row Echelon Form (RREF).<br>• Back-substitute to find solutions. |
| **6** | **Solution Structure and Rank** | 1. Rank and Null Space<br>2. Pivot and Free Variables | • Determine Rank from RREF.<br>• Identify pivot and free variables.<br>• Express the general solution (particular + homogeneous).<br>• Understand the Null Space as the solution to $A\mathbf{x} = \mathbf{0}$. |

### 10-Point Concept Checklist Before Numerical Linear Algebra

Before moving to numerical linear algebra (which focuses on algorithms, stability, and approximation), ensure you can solidly execute and explain these 10 concepts:

1. [ ] **Vector Arithmetic**: Fluently add vectors and multiply by scalars; understand vector norms.
2. [ ] **Dot Product**: Correctly calculate dot products and use them to test for orthogonality.
3. [ ] **Matrix-Vector Multiplication**: Interpret $A\mathbf{x}$ both as row operations and column linear combinations.
4. [ ] **Matrix-Matrix Multiplication**: Perform products correctly and understand the dimensions rule ($m \times n$ times $n \times p$).
5. [ ] **Augmented Matrices**: Efficiently convert systems of equations into augmented matrix form.
6. [ ] **Row Operations**: Execute row swaps, scaling, and addition without arithmetic errors.
7. [ ] **Gaussian Elimination**: Systematically reduce a matrix to REF and RREF.
8. [ ] **Rank Identification**: Correctly identify the rank of a matrix from its RREF.
9. [ ] **Null Space Analysis**: Parametrize the solution space of a homogeneous system ($A\mathbf{x}=0$) using free variables.
10. [ ] **Invertibility**: Determine invertibility via RREF (no zeros in diagonal) or Determinant, and compute the inverse for small systems.

## 7-Day Study Schedule

| Day | Primary Topics | Key Concepts | Suggested Activities |
| :--- | :--- | :--- | :--- |
| **1** | **Foundations of Vectors and Matrices** | • Scalar and Vector Arithmetic (Addition, Scalar Multiplication)<br>• Matrix Definition and Notation (Rows, Columns, Dimensions) | • Practice vector addition and scalar multiplication.<br>• Identify matrix dimensions and specific entries.<br>• Review how matrices relate to vectors (columns/rows). |
| **2** | **Vector Metrics & Basic Matrix Ops** | • Dot Product and Norms (Euclidean norm, orthogonality)<br>• Matrix Addition and Scalar Multiplication | • Calculate dot products and vector norms.<br>• Add matrices and multiply by scalars.<br>• Explore geometric interpretations of the dot product. |
| **3** | **Matrix Multiplication** | • Matrix-Vector Multiplication (Linear combination of columns)<br>• Matrix-Matrix Multiplication (Composition of linear maps) | • Compute $A\mathbf{x}$ and $AB$.<br>• Analyze matrix multiplication as a series of dot products.<br>• Verify non-commutativity ($AB \neq BA$) with examples. |
| **4** | **Systems of Linear Equations** | • Systems of Linear Equations and Augmented Matrices<br>• Consistency and Geometric Interpretation | • Translate systems of equations into matrix form $A\mathbf{x} = \mathbf{b}$.<br>• Construct and interpret augmented matrices.<br>• Visualize solutions as intersecting lines or planes. |
| **5** | **Solving Systems via Elimination** | • Gaussian Elimination<br>• Row Reduction (REF and RREF) | • Apply elementary row operations (swap, scale, add).<br>• Reduce matrices to Row Echelon Form (REF) and Reduced Row Echelon Form (RREF).<br>• Back-substitute to find solutions. |
| **6** | **Solution Structure and Rank** | • Rank and Null Space<br>• Pivot and Free Variables | • Determine Rank from the RREF of a matrix.<br>• Identify pivot and free variables.<br>• Express the general solution (particular + homogeneous).<br>• Analyze the Null Space as the solution to $A\mathbf{x} = \mathbf{0}$. |

## 10-Concept Prerequisite Checklist

1. **Matrix-Vector Multiplication**: Essential for defining linear transformations and implementing iterative solvers like Krylov subspace methods.
2. **Systems of Linear Equations**: The primary problem class in numerical linear algebra, requiring understanding of solution existence and uniqueness.
3. **Gaussian Elimination and Row Reduction**: Foundational for direct solvers and determining matrix rank and invertibility in finite precision arithmetic.
4. **Rank**: Determines the solvability of systems and the structure of least-squares problems, critical for rank-revealing decompositions.
5. **Vector Spaces and Subspaces**: Provides the geometric framework for understanding solution sets and approximations in finite-dimensional spaces.
6. **Linear Independence**: Crucial for determining basis viability and avoiding instability in linear system solutions.
7. **Orthogonality and Projection**: Key to stable algorithms like QR factorization and solving least-squares problems via projections.
8. **Eigenvalues and Eigenvectors**: Fundamental for analyzing matrix behavior in iterative methods and assessing stability via spectral radius.
9. **Matrix Norms** (implied under Dot Product and Norms): Essential for quantifying error, stability, and conditioning in numerical computations.
10. **Matrix Inversion**: While rarely computed directly, understanding it is vital for analyzing system conditioning and formulating inverse problems.
