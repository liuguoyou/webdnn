from typing import List

from graph_transpiler.backend.webgpu.allocator import MemoryLayout
from graph_transpiler.backend.webgpu.kernel import GPUSize, Kernel
from graph_transpiler.backend.webgpu.kernels import util
from graph_transpiler.backend.webgpu.meta_buffer_injector import MetaBufferInjector
from graph_transpiler.graph.operators.scalar_affine import ScalarAffine

template = """
kernel void %%FUNC_NAME%%(device float *data_buffer[[buffer(0)]],
                          const device int * %%META_NAME%% [[buffer(1)]],
                          uint index[[thread_position_in_grid]],
                          uint num_threads[[threads_per_grid]])
{
    const device float *X = data_buffer + %%META_LOAD(affine_transform_X_offset)%%;
    device float *Y = data_buffer + %%META_LOAD(affine_transform_Y_offset)%%;

    const float scale = *((const device float *)(& %%META_LOAD(affine_transform_scale)%%));
    const float bias = *((const device float *)(& %%META_LOAD(affine_transform_bias)%%));
    const int N = %%META_LOAD(affine_transform_N)%%;

    for (int gid = index; gid < N; gid += num_threads) {
        float result = X[gid];
        result = result * scale + bias;
        
        Y[gid] = result;
    }
}
"""


# noinspection PyUnusedLocal
def scalar_affine(op: ScalarAffine,
                  memory_layout: MemoryLayout,
                  metabuffer_injector: MetaBufferInjector = None) -> List[Kernel]:
    x = memory_layout[op.inputs["x"]]
    y = memory_layout[op.outputs["y"]]
    assert x.variable.shape == y.variable.shape

    if metabuffer_injector is None:
        metabuffer_injector = MetaBufferInjector()
    metabuffer_injector.register({
        "affine_transform_X_offset": x.offset,
        "affine_transform_Y_offset": y.offset,
        "affine_transform_N": y.variable.size,
        "affine_transform_scale": op.scale,
        "affine_transform_bias": op.bias
    })

    source = metabuffer_injector.inject(template)
    func_name = util.add_canonical_suffix("scalar_affine", source)
    source = source.replace("%%FUNC_NAME%%", func_name)

    kernel = Kernel(
        {func_name: source},
        func_name,
        GPUSize(8, 1, 1),
        GPUSize(1024, 1, 1),
        metabuffer_injector.generate_buffer()
    )

    return [kernel]
