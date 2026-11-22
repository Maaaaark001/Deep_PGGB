#include <cstdio>
#include <cmath>
#include <fftw3.h>
int main(){
  int n=1024;
  double* in=(double*)fftw_malloc(sizeof(double)*n);
  fftw_complex* out=(fftw_complex*)fftw_malloc(sizeof(fftw_complex)*(n/2+1));
  for(int i=0;i<n;i++) in[i]=sin(2*M_PI*8*i/n);
  fftw_plan p=fftw_plan_dft_r2c_1d(n,in,out,FFTW_ESTIMATE);
  fftw_execute(p);
  printf("bin8=%.3f bin9=%.3f threads=%d\n", out[8][0], out[9][0], fftw_init_threads());
  fftw_destroy_plan(p); fftw_free(in); fftw_free(out);
  return 0;
}